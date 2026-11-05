import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cloudDemo,demoResponse} from '../lib/demo.mjs';
test('cloud demo persists at least 200 products and never pretends saved history exists',async()=>{
 assert.equal(cloudDemo({}),true);assert.equal(cloudDemo({BACKEND_API_URL:'https://example.com'}),false);
 let r=await demoResponse(new Request('https://demo.example/api/backend/products'),['products']);assert.ok((await r.json()).total>=200);
 r=await demoResponse(new Request('https://demo.example/api/backend/recommendations'),['recommendations']);assert.deepEqual((await r.json()).items,[]);
});
test('demo search grounds product facts and applies a natural budget',async()=>{
 const r=await demoResponse(new Request('https://demo.example/api/backend/rag/search',{method:'POST',body:JSON.stringify({query:'wireless headphones under INR 3000'})}),['rag','search']);
 const d=await r.json();assert.ok(d.items.length);assert.equal(d.llm_used,false);assert.ok(d.items.every(i=>Number(i.product.price)<=3000));assert.equal(d.generation,'cloud_demo_lexical');
});
test('demo rejects writes, malformed queries, cross-origin access and unmatched evidence',async()=>{
 const req=(body,origin='https://demo.example')=>new Request('https://demo.example/api/backend/rag/search',{method:'POST',body,headers:{origin}});
 assert.equal((await demoResponse(req('{}'),['recommendations'])).status,403);
 assert.equal((await demoResponse(req('{'),['rag','search'])).status,422);
 assert.equal((await demoResponse(req('{}','https://other.example'),['rag','search'])).status,403);
 const d=await (await demoResponse(req(JSON.stringify({query:'zzqqxxunmatched'})),['rag','search'])).json();assert.equal(d.items.length,0);
});
