// Deliberately narrow gateway. Never accepts a client-selected upstream URL or headers.
export function permitted(method, path, savedGeneration = false) {
  if (method === 'GET') return /^(health|ready|products|products\/search|products\/[A-Za-z0-9_-]+|customers|customers\/[A-Za-z0-9_-]+(?:\/preferences|\/history)?|recommendations(?:\/\d+)?|analytics\/(?:overview|recommendations|channels)|rag\/status|agents\/(?:status|definition)|agents\/runs\/[A-Za-z0-9_-]+)$/.test(path);
  return method === 'POST' && (path === 'rag/search' || (savedGeneration && ['recommendations', 'agents/run'].includes(path)));
}

export async function proxy(request, segments, env = process.env, transport = fetch) {
  const path = segments.join('/');
  if (segments.some(part => !/^[A-Za-z0-9_-]+$/.test(part)) || !permitted(request.method, path, env.ENABLE_SAVED_GENERATION === 'true'))
    return Response.json({ detail: 'This operation is not enabled in the deployment frontend.' }, { status: 403 });
  const origin = request.headers.get('origin');
  if (request.method !== 'GET' && origin && origin !== new URL(request.url).origin)
    return Response.json({ detail: 'Cross-origin requests are not accepted.' }, { status: 403 });
  let base;
  try {
    base = new URL(env.BACKEND_API_URL || '');
    const local = ['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname);
    if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
        (base.protocol !== 'https:' && !(base.protocol === 'http:' && local && !env.VERCEL))) throw new Error();
    if (local && env.VERCEL) throw new Error();
  } catch {
    return Response.json({ detail: 'Backend is not configured. Set the server-side BACKEND_API_URL to its HTTPS origin.' }, { status: 503 });
  }
  const target = new URL('/' + path, base);
  target.search = new URL(request.url).search;
  try {
    const body = request.method === 'POST' ? await request.text() : undefined;
    if (body && Buffer.byteLength(body) > 64 * 1024) return Response.json({ detail: 'Request is too large.' }, { status: 413 });
    const response = await transport(target, { method: request.method, body, headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
      redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(45000) });
    const headers = { 'Content-Type': response.headers.get('content-type') || 'application/json', 'Cache-Control': 'no-store' };
    return new Response(await response.arrayBuffer(), { status: response.status, headers });
  } catch {
    return Response.json({ detail: 'Backend unavailable or timed out. For saved operations, inspect history before retrying.' }, { status: 502 });
  }
}
