# Safe GitHub upload — commands for the project owner

No commit, remote change, push, GitHub repository creation, or hosting deployment was performed by this preparation.

## Audit findings

- Git is initialized. Current branch is the unborn `master` branch; there are no commits and no tracked/staged files.
- No Git remote is configured.
- The provided remote `https://github.com/lachaiahgarivaishnavi18-droid/RetailRAG-AI.git` was inspected read-only. It has `main` at `6962506df6af8a11dc68d6735779f2b099a377f4`, containing only `README.md`. No remote was added locally.
- `.gitignore` now excludes dependency caches (including the previously exposed `.pnpm-store`), `.env` files, Streamlit secrets, credential files/private keys, SQLite databases/journals, backup directories/archives, virtual environments, generated frontend output, and local runtime/test files.
- Blank `.env.example` files, synthetic demo CSVs, source/tests, deployment files, dependency lockfile, original product photographs, and attribution remain upload candidates.
- Upload-candidate text was scanned for common provider tokens, private-key headers, credential URLs, and literal environment secrets. Three hits were manually verified: a placeholder PostgreSQL URL in README, a dummy credential URL in a proxy test, and a `SecretStr` type declaration. No real credential was detected by these checks; pattern scanning is not a guarantee against every possible secret format.
- Deployment/frontend JSON/YAML parsed successfully. The pnpm lockfile matches package dependency specifiers. All 24 original photo files match their manifest hashes. Five proxy tests and a read-only TypeScript check passed during this audit.
- Git data and source project records were not deleted. Nothing was staged. A Git staging dry-run was unavailable because the managed workspace denies writing `.git/index.lock`; the candidate review instead used read-only `git ls-files --cached --others --exclude-standard`.

## Before running upload commands

Your repository already has an initial README commit. The commands below preserve it as Git history, retain the complete local project README, and upload a new **`codex/retailrag-import` branch**. They do not overwrite remote `main`. After upload, review and merge a pull request from that branch into `main` on GitHub.

If the remote gains other files before you run these commands, the file-list guard stops the import so those changes can be reconciled deliberately. Do not use `--force` or reset your project to make an upload succeed.

Git-ignored databases and backups **will not be uploaded**. Keep them backed up privately and restore them separately when hosting the backend. Source control is not a backup of the current recommendation/customer history. Check [the deployment plan](README.md) before creating any hosting services; importing a Render Blueprint can provision paid services even with commit-triggered auto-deploys off.

## Windows PowerShell: inspect and stage locally

These commands are provided for you to execute. They have not been run as staging/commit/upload actions.

```powershell
Set-Location 'C:\Users\ADMIN\Documents\ChatGPT\RetailRAG AI 3'

git status --short
git remote -v
git config user.name
git config user.email
# If either identity value is missing, set your intended identity locally:
# git config user.name 'Your Name'
# git config user.email 'YOUR_GITHUB_NOREPLY_EMAIL'

# Inspect exactly what is eligible, without staging or printing file contents:
git ls-files --cached --others --exclude-standard

# Confirm sensitive/generated examples are ignored:
git check-ignore .env frontend/.env.local .streamlit/secrets.toml data/retailrag.db data/chroma/retailrag_products.json backups/retailrag.zip .venv/pyvenv.cfg .pnpm-store/cache frontend/node_modules/react/package.json frontend/.next/BUILD_ID

# Stage only the reviewed project directories/files; ignore rules still apply:
git add -- .gitignore .env.example .streamlit/config.toml README.md pyproject.toml src tests assets data deploy frontend
if ($LASTEXITCODE -ne 0) { throw 'Staging failed. Stop and resolve the error; do not force-add files.' }

# REVIEW this output before committing. No .env, .db, backup, key or cache belongs here.
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
```

If an unwanted path appears, unstage that specific path without deleting the local file, then fix its ignore rule:

```powershell
# Example only; replace the path with the specific unwanted staged file.
git rm --cached -- 'PATH_TO_UNWANTED_STAGED_FILE'
```

Do not use `git add -f`, `git clean`, recursive delete commands, or broad file-removal commands.

## Windows PowerShell: connect the existing remote and preserve its history

Run this block only after reviewing the staged list above. The URL below is the repository supplied by the project owner. GitHub authentication should happen through Git Credential Manager/browser sign-in, not by putting credentials in the URL or a project file.

```powershell
$repoUrl = 'https://github.com/lachaiahgarivaishnavi18-droid/RetailRAG-AI.git'
if ($repoUrl -notmatch '^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$') {
  throw 'Use a normal github.com HTTPS repository URL without embedded credentials.'
}

if (git remote) { throw 'A remote is already configured. Inspect it before changing anything.' }

git commit -m 'Prepare RetailRAG AI application and deployment configuration'
if ($LASTEXITCODE -ne 0) { throw 'Commit failed. Resolve the issue before continuing.' }
git branch -m codex/retailrag-import
if ($LASTEXITCODE -ne 0) { throw 'Branch rename failed. Inspect local branches before continuing.' }
git remote add origin $repoUrl
if ($LASTEXITCODE -ne 0) { throw 'Remote configuration failed. Inspect git remote -v.' }
git remote -v
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed. Check repository access/authentication before continuing.' }

$remoteFiles = @(git ls-tree -r --name-only origin/main)
if ($LASTEXITCODE -ne 0 -or $remoteFiles.Count -ne 1 -or $remoteFiles[0] -ne 'README.md') {
  throw 'Remote contents differ from the reviewed initial README. Stop and review before merging.'
}

# This normally reports an add/add README conflict. That is expected; stop here.
git merge --no-commit --no-ff --allow-unrelated-histories origin/main
```

Inspect conflicts:

```powershell
git status --short
git diff --name-only --diff-filter=U
```

**Only if `README.md` is the sole conflict**, keep the complete local README. Its original local contents are already saved in the first commit; the GitHub README remains preserved in the fetched commit and merge history. These commands do not remove application data:

```powershell
git checkout --ours -- README.md
git add -- README.md
```

If other files conflict, stop and reconcile them individually. If the merge completed without conflicts, skip the two conflict-resolution commands. Once there are no unresolved paths:

```powershell
git diff --name-only --diff-filter=U
git diff --cached --check
git commit -m 'Merge existing GitHub README history into RetailRAG import'
if ($LASTEXITCODE -ne 0) { throw 'Merge commit failed. Resolve remaining conflicts before uploading.' }

# Preview the proposed branch upload, then upload only when ready:
git push --dry-run origin codex/retailrag-import
if ($LASTEXITCODE -ne 0) { throw 'Push preview failed. Stop; do not force-push.' }
git push -u origin codex/retailrag-import
if ($LASTEXITCODE -ne 0) { throw 'Push failed. Inspect the error; do not force-push.' }
```

Open GitHub and create a pull request from `codex/retailrag-import` into `main`. Review its file list and merge it when satisfied. This preserves the initial GitHub commit and the imported project snapshot. The original local database/Chroma data remain outside source control.

After upload, GitHub stores the reviewed source/assets. It does not automatically mean Vercel or Render is deployed. For a later Vercel import use root directory `frontend` and enable access to repository files outside that root for the original photo assets.

Official guidance: [Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github), [Managing remotes](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories).
