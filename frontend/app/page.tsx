import Workspace from '../components/workspace';
export const dynamic = 'force-dynamic';
export default function Page() {
  let streamlit = '';
  try { const url = new URL(process.env.STREAMLIT_APP_URL || ''); if (url.protocol === 'https:' || (!process.env.VERCEL && url.protocol === 'http:' && url.hostname === '127.0.0.1')) streamlit = url.href; } catch {}
  return <Workspace streamlitUrl={streamlit} generationEnabled={process.env.ENABLE_SAVED_GENERATION === 'true'} />;
}
