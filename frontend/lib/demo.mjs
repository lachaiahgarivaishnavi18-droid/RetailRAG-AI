import data from './demo-data.json' with { type: 'json' };

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
      const q=(url.searchParams.get('q')||'').toLowerCase(),category=url.searchParams.get('category');
      const items=data.products.filter(p=>(!q||`${p.name} ${p.description} ${p.category} ${p.brand}`.toLowerCase().includes(q))&&(!category||p.category===category)&&(!(url.searchParams.get('available')==='true')||p.available));
      return reply({...page(items),items:items.slice(0,100)});
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
  const query=input.query.toLowerCase();
  const words=tokens(query).filter(t=>!['a','an','the','for','under','below','above','over','inr','with','and','what','which','is','are','me','show','find','please'].includes(t)&&!/^\d+$/.test(t));
  const maximum=query.match(/(?:under|below|up to)\s*(?:inr|rs\.?|₹)?\s*([\d,]+)/i);
  const minimum=query.match(/(?:above|over)\s*(?:inr|rs\.?|₹)?\s*([\d,]+)/i);
  const max=input.max_price??(maximum?Number(maximum[1].replaceAll(',','')):Infinity);
  const min=input.min_price??(minimum?Number(minimum[1].replaceAll(',','')):0);
  const matches=data.products.filter(p=>(input.available_only===false||p.available)&&Number(p.price)<=Number(max)&&Number(p.price)>=Number(min)&&(!input.category||p.category.toLowerCase()===String(input.category).toLowerCase())&&(!input.brand||p.brand.toLowerCase()===String(input.brand).toLowerCase())).map(p=>{
    const evidence=`${p.name} ${p.category} ${p.description} ${p.features.join(' ')}`;
    const terms=new Set(tokens(evidence));const matched=words.filter(w=>terms.has(w));
    return {p,evidence,score:words.length?matched.length/words.length:1};
  }).filter(r=>r.score>0).sort((a,b)=>b.score-a.score||b.p.rating-a.p.rating||Number(a.p.price)-Number(b.p.price)).slice(0,Math.min(20,Math.max(1,Number(input.limit)||5)));
  const items=matches.map(({p,evidence,score},i)=>({rank:i+1,product:p,relevance_score:score,document:evidence,document_id:`demo:${p.id}`,explanation:'Matched terms in the bundled synthetic catalog; price and availability filters were applied.'}));
  return reply({generation:'cloud_demo_lexical',llm_used:false,llm_attempted:false,items,references:items.map(i=>i.product.id),warnings:['Read-only cloud demo: lexical search, not the local Chroma/LangGraph engine. Customer personalization and saved history are unavailable here.'],answer:items.length?'Here are catalog matches supported by the bundled product information:\n'+items.map(i=>`[${i.product.id}] ${i.product.name}: INR ${i.product.price}, ${i.product.stock_quantity} in stock.`).join('\n'):'No catalog evidence matched your request and filters.'});
}
