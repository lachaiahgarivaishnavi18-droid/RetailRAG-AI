import { test } from 'node:test';
import assert from 'node:assert/strict';
import { proxy, permitted } from '../lib/proxy.mjs';

const env = { BACKEND_API_URL: 'https://backend.example.com', VERCEL: '1' };
test('allowlist matches real API routes without exposing catalog mutation or ingestion',()=>{
  for(const path of ['health','ready','products','products/search','products/P001','customers/C001/preferences','recommendations/18','rag/status','analytics/overview','agents/status'])assert.equal(permitted('GET',path),true,path);
  for(const [method,path] of [['POST','products'],['DELETE','products/P001'],['POST','rag/ingest'],['POST','tools/save_recommendation/execute'],['GET','settings']])assert.equal(permitted(method,path,true),false,path);
  assert.equal(permitted('POST','rag/search'),true);
  assert.equal(permitted('POST','recommendations'),false);
  assert.equal(permitted('POST','recommendations',true),true);
});
test('upstream path/query and HTTP errors are preserved, credentials are not forwarded',async()=>{
  const request=new Request('https://frontend.example.com/api/backend/products?q=headphones&limit=9',{headers:{cookie:'private',authorization:'private'}});
  const response=await proxy(request,['products'],env,async(url,options)=>{
    assert.equal(String(url),'https://backend.example.com/products?q=headphones&limit=9');
    assert.equal(options.headers.authorization,undefined);assert.equal(options.headers.cookie,undefined);
    assert.equal(options.cache,'no-store');assert.equal(options.redirect,'error');
    return Response.json({detail:'Product not found'},{status:404});
  });
  assert.equal(response.status,404);assert.deepEqual(await response.json(),{detail:'Product not found'});assert.equal(response.headers.get('cache-control'),'no-store');
});
test('missing URL, remote HTTP and production localhost fail without leaking configuration',async()=>{
  for(const config of [{},{BACKEND_API_URL:'http://backend.example.com'},{...env,BACKEND_API_URL:'http://127.0.0.1:8000'},{BACKEND_API_URL:'https://user:password@backend.example.com'}]){
    const result=await proxy(new Request('https://frontend.example.com/api/backend/ready'),['ready'],config,()=>{throw new Error('must not fetch');});
    assert.equal(result.status,503);assert.equal((await result.text()).includes('password'),false);
  }
});
test('path escape, cross-origin writes and disabled writes never reach backend',async()=>{
  const transport=()=>{throw new Error('must not fetch');};
  assert.equal((await proxy(new Request('https://frontend.example.com/api/backend/products'),['..','products'],env,transport)).status,403);
  assert.equal((await proxy(new Request('https://frontend.example.com/api/backend/recommendations',{method:'POST',body:'{}'}),['recommendations'],env,transport)).status,403);
  assert.equal((await proxy(new Request('https://frontend.example.com/api/backend/rag/search',{method:'POST',body:'{}',headers:{origin:'https://other.example.com'}}),['rag','search'],env,transport)).status,403);
});
test('RAG search uses current POST contract; private provider errors remain server-side',async()=>{
  const request=()=>new Request('https://frontend.example.com/api/backend/rag/search',{method:'POST',body:'{"query":"headphones"}',headers:{origin:'https://frontend.example.com'}});
  const result=await proxy(request(),['rag','search'],env,async(url,options)=>{
    assert.equal(String(url),'https://backend.example.com/rag/search');assert.equal(options.body,'{"query":"headphones"}');return Response.json({items:[],llm_used:false});
  });
  assert.equal(result.status,200);
  const failed=await proxy(request(),['rag','search'],env,async()=>{throw new Error('private upstream data');});
  assert.equal(failed.status,502);assert.equal((await failed.text()).includes('private upstream data'),false);
});
