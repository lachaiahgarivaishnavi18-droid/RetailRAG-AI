import data from './demo-data.json' with { type: 'json' };
import {searchCatalog} from './catalog-search.mjs';

const tokens = text => text.toLowerCase().match(/[a-z0-9]+/g) || [];
const page = items => ({total:items.length,items});
export function cloudDemo(env=process.env) {
  return !env.BACKEND_API_URL && env.VERCEL_DEMO_MODE !== 'false';
}
export async function demoResponse(request, segments) {
  const path=segments.join('/'), url=new URL(request.url);
  const reply=(body,status=200)=>Response.json(body,{status,headers:{'Cache-Control':'no-store'}});
  if(request.method==='GET') {
    if(['health','ready'].includes(path))return reply({status:path==='ready'?'ready':'ok',mode:'cloud_demo'});
    if(path==='customers')return reply(page(data.customers));
    if(path==='recommendations')return reply(page([]));
    if(path==='products') {
      const params=url.searchParams;
      const numeric=name=>params.has(name)?Number(params.get(name)):undefined;
      const min=numeric('min_price'),max=numeric('max_price'),offset=numeric('offset')??0,limit=numeric('limit')??9;
      if([min,max].some(v=>v!==undefined&&(!Number.isFinite(v)||v<0))||(min!==undefined&&max!==undefined&&min>max)||!Number.isInteger(offset)||offset<0||!Number.isInteger(limit)||limit<1||limit>100)return reply({detail:'Invalid price range or pagination.'},422);
      const items=searchCatalog(data.products,{query:params.get('q')||'',category:params.get('category')||'',available:params.get('available')==='true',min,max}).map(r=>r.product);
      return reply({total:items.length,items:items.slice(offset,offset+limit),offset,limit,categories:[...new Set(data.products.map(p=>p.category))].sort()});
    }
    if(path==='analytics/overview') {
      const byId=Object.fromEntries(data.products.map(p=>[p.id,p]));
      const categories={},channels={};
      for(const event of data.interactions){const category=byId[event.product_id]?.category;if(category)categories[category]=(categories[category]||0)+1;channels[event.channel]=(channels[event.channel]||0)+1;}
      return reply({totals:{products:data.products.length,customers:data.customers.length,recommendations:0,interactions:data.interactions.length},popular_categories:Object.entries(categories).map(([category,count])=>({category,count})).sort((a,b)=>b.count-a.count),channel_activity:Object.entries(channels).map(([channel,interactions])=>({channel,interactions})),mode:'cloud_demo'});
    }
    return reply({detail:'This feature needs the separately hosted Python backend.'},503);
  }
  if(request.method!=='POST'||path!=='rag/search')return reply({detail:'Cloud demo is read-only. Saved workflows remain available in the local application.'},403);
  const origin=request.headers.get('origin');
  if(origin&&origin!==url.origin)return reply({detail:'Cross-origin requests are not accepted.'},403);
  const body=await request.text();if(Buffer.byteLength(body)>65536)return reply({detail:'Request too large.'},413);
  let input;try{input=JSON.parse(body);}catch{return reply({detail:'Invalid JSON.'},422);}
  if(typeof input.query!=='string'||!input.query.trim()||input.query.length>2000)return reply({detail:'Enter a question of 1–2000 characters.'},422);
  const matches=searchCatalog(data.products,{query:input.query,category:input.category,brand:input.brand,available:input.available_only!==false,min:input.min_price,max:input.max_price}).slice(0,Math.min(20,Math.max(1,Number(input.limit)||5))).map(({product:p,score})=>({p,score,evidence:`${p.name} ${p.category} ${p.description} ${p.features.join(' ')}`}));
  const items=matches.map(({p,evidence,score},i)=>({rank:i+1,product:p,relevance_score:score,document:evidence,document_id:`demo:${p.id}`,explanation:'Matched terms in the bundled synthetic catalog; price and availability filters were applied.'}));
  return reply({generation:'cloud_demo_lexical',llm_used:false,llm_attempted:false,items,references:items.map(i=>i.product.id),warnings:['Read-only cloud demo: lexical search, not the local Chroma/LangGraph engine. Customer personalization and saved history are unavailable here.'],answer:items.length?'Here are catalog matches supported by the bundled product information:\n'+items.map(i=>`[${i.product.id}] ${i.product.name}: INR ${i.product.price}, ${i.product.stock_quantity} in stock.`).join('\n'):'No catalog evidence matched your request and filters.'});
}
