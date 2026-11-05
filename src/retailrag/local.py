"""Credential-free local launcher: python -m retailrag.local."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retailrag.config import Settings
from retailrag.database import build_engine, initialize_database
from retailrag.ingestion import import_directory
from retailrag.models import Product
from retailrag.rag_store import RagStore


ROOT = Path(__file__).resolve().parents[2]


def available_port(first):
    for port in range(first, min(first + 100, 65536)):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available local port in the requested range")


def prepare(settings):
    engine = build_engine(settings.database_url)
    try:
        initialize_database(engine)
        with Session(engine) as session:
            empty = session.scalar(select(func.count()).select_from(Product)) == 0
        if empty:
            import_directory(engine, ROOT / "data/demo", "synthetic_demo")
        store = RagStore(settings)
        with Session(engine) as session:
            if store.load() is None:
                store.ingest(session)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8514)
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()
    os.chdir(ROOT)
    api_port = available_port(args.api_port)
    ui_port = available_port(args.port if args.port != api_port else args.port + 1)
    env = os.environ.copy()
    # Local startup is intentionally independent from deployment/migration URIs.
    env.update(RETAILRAG_DATABASE_URL="sqlite:///./data/retailrag.db",
               RETAILRAG_RAG_DIRECTORY="data/chroma", RETAILRAG_ENVIRONMENT="development",
               RETAILRAG_API_BASE_URL=f"http://127.0.0.1:{api_port}")
    settings = Settings(database_url=env["RETAILRAG_DATABASE_URL"], rag_directory=Path("data/chroma"))
    prepare(settings)
    children = []
    try:
        children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "retailrag.api:app", "--host", "127.0.0.1", "--port", str(api_port)], env=env))
        for _ in range(120):
            if children[0].poll() is not None:
                raise RuntimeError("Backend exited during startup")
            try:
                if httpx.get(f"http://127.0.0.1:{api_port}/ready", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Backend did not become ready")
        children.append(subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "src/retailrag/frontend.py"), "--server.address", "127.0.0.1", "--server.port", str(ui_port), "--server.headless", "true", "--browser.gatherUsageStats", "false"], env=env))
        state = {"frontend": f"http://127.0.0.1:{ui_port}", "backend": f"http://127.0.0.1:{api_port}", "pid": os.getpid()}
        (ROOT / ".runtime").mkdir(exist_ok=True)
        (ROOT / ".runtime/local-server.json").write_text(json.dumps(state), encoding="utf-8")
        print(json.dumps(state), flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)


if __name__ == "__main__":
    main()
