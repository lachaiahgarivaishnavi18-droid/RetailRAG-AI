import Workspace from '../components/workspace';
import { cloudDemo } from '../lib/demo.mjs';
export const dynamic = 'force-dynamic';
export default function Page() {
  let streamlit = '';
  try { const url = new URL(process.env.STREAMLIT_APP_URL || ''); if (url.protocol === 'https:' || (!process.env.VERCEL && url.protocol === 'http:' && url.hostname === '127.0.0.1')) streamlit = url.href; } catch {}
  return <Workspace streamlitUrl={streamlit} demoMode={cloudDemo()} generationEnabled={!cloudDemo() && process.env.ENABLE_SAVED_GENERATION === 'true'} />;
}
