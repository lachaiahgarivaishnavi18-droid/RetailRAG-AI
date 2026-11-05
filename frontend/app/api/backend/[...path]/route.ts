import { proxy } from '../../../../lib/proxy.mjs';
import { cloudDemo, demoResponse } from '../../../../lib/demo.mjs';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 60;
type Context = { params: Promise<{ path: string[] }> };
export async function GET(request: Request, context: Context) { const path=(await context.params).path; return cloudDemo()?demoResponse(request,path):proxy(request,path); }
export async function POST(request: Request, context: Context) { const path=(await context.params).path; return cloudDemo()?demoResponse(request,path):proxy(request,path); }
