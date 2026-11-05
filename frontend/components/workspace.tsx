'use client';

import { useEffect, useState } from 'react';

type Product = { id: string; name: string; description: string; category: string; brand: string; price: string; rating: number; stock_quantity: number; available: boolean; features: string[]; attributes: Record<string,string>; image_url?: string };
type Item = { rank: number; product: Product; explanation: string; relevance_score: number; document?: string; document_id?: string };
type Result = { id?: number; message?: string; answer?: string; generation?: string; llm_used?: boolean; items: Item[]; warnings?: string[]; profile?: unknown; references?: string[] };
type Photo = { name: string; category: string; description: string; src: string; alt: string; photographer: string; source_url: string };
type History = { id: number; query: string; customer_id: string | null; channel: string; created_at: string; item_count: number };
type Overview = { totals: { products: number; customers: number; recommendations: number; interactions: number }; popular_categories: { category: string; count: number }[]; channel_activity: {channel: string; interactions: number}[] };
type Workflow = { run_id: string; status: string; output: Result | null; error?: string; steps: {agent: string; status: string; duration_ms: number | null}[] };
type Page<T> = { total: number; items: T[] };

async function api<T>(path: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/backend/' + path, { signal, cache:'no-store', ...(payload ? { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) } : {}) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || 'Request failed'));
  return data as T;
}

function ProductCard({product:p, item, photo}: {product:Product; item?:Item; photo?:Photo}) {
  const [broken, setBroken] = useState(false);
  const image = photo?.name === p.name && photo.category === p.category && photo.description === p.description ? photo : undefined;
  return <article className="product">
    {image && !broken ? <img src={image.src} alt={image.alt} width="960" height="720" onError={()=>setBroken(true)} /> : <div className="photo-empty">Product photograph unavailable</div>}
    <div className="product-copy"><span className="eyebrow">{p.category} / {p.brand}</span><h3>{item && <span className="rank">{item.rank}</span>}{p.name}</h3>
      <div className="price">₹{Number(p.price).toLocaleString('en-IN')} <span>★ {p.rating.toFixed(1)}</span></div>
      <span className={p.available?'stock':'unavailable'}>{p.available?`${p.stock_quantity} in stock`:'Out of stock'}</span><p>{p.description}</p>
      {item && <div className="evidence"><strong>Why this match</strong><p>{item.explanation}</p><small>Relevance {item.relevance_score.toFixed(3)} · ranking signal</small></div>}
      <details><summary>Details & evidence</summary><ul>{p.features.map(f=><li key={f}>{f}</li>)}</ul><dl>{Object.entries(p.attributes).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        {item?.document && <><strong>{item.document_id}</strong><p>{item.document}</p></>}
        {image && <p className="muted">Representative stock photo by {image.photographer}. <a href={image.source_url} target="_blank" rel="noreferrer">Original source</a>. Fictional catalog brand.</p>}
      </details>
    </div>
  </article>;
}

const SECTIONS = ['Dashboard','Product Discovery','AI Shopping Assistant','Recommendations','Agent Workflow','Recommendation History'];

export default function Workspace({streamlitUrl,generationEnabled,demoMode=false}:{streamlitUrl:string;generationEnabled:boolean;demoMode?:boolean}) {
  const [section,setSection]=useState('Dashboard');
  const [overview,setOverview]=useState<Overview|null>(null);
  const [products,setProducts]=useState<Product[]>([]);
  const [totalProducts,setTotalProducts]=useState(0);
  const [photos,setPhotos]=useState<Record<string,Photo>>({});
  const [customers,setCustomers]=useState<{id:string;name:string}[]>([]);
  const [history,setHistory]=useState<History[]>([]);
  const [result,setResult]=useState<Result|null>(null);
  const [workflow,setWorkflow]=useState<Workflow|null>(null);
  const [query,setQuery]=useState('');
  const [customer,setCustomer]=useState('');
  const [channel,setChannel]=useState('ecommerce');
  const [category,setCategory]=useState('');
  const [available,setAvailable]=useState(false);
  const [page,setPage]=useState(1);
  const [minPrice,setMinPrice]=useState('');
  const [maxPrice,setMaxPrice]=useState('');
  const [appliedFilters,setAppliedFilters]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [connected,setConnected]=useState(false);

  useEffect(()=>{
    const controller=new AbortController();
    setBusy(true);
    Promise.all([
      api<{status:string}>('ready',undefined,controller.signal),
      api<Overview>('analytics/overview',undefined,controller.signal),
      api<Page<Product>>('products?limit=9',undefined,controller.signal),
      api<Page<{id:string;name:string}>>('customers?limit=100',undefined,controller.signal),
      api<Page<History>>('recommendations?limit=20',undefined,controller.signal),
      fetch('/product-photos.json',{signal:controller.signal}).then(r=>{if(!r.ok)throw new Error('Photo mapping unavailable');return r.json() as Promise<Record<string,Photo>>;})
    ]).then(([ready,metrics,catalog,people,saved,images])=>{
      setConnected(ready.status==='ready');setOverview(metrics);setProducts(catalog.items);setTotalProducts(catalog.total);
      setCustomers(people.items);setHistory(saved.items);setPhotos(images);
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
    return ()=>controller.abort();
  },[]);

  async function loadCatalog(nextPage:number, filters=appliedFilters) {
    const params=new URLSearchParams(filters);params.set('limit','9');params.set('offset',String((nextPage-1)*9));
    const catalog=await api<Page<Product>>('products?'+params);
    setProducts(catalog.items);setTotalProducts(catalog.total);setPage(nextPage);setAppliedFilters(filters);
  }
  async function browse(nextPage:number) {
    setBusy(true);setError('');
    try {await loadCatalog(nextPage);}catch(e){setError(e instanceof Error?e.message:'Catalog unavailable.');}finally{setBusy(false);}
  }

  async function submit(event:React.FormEvent) {
    event.preventDefault();setError('');setBusy(true);setResult(null);setWorkflow(null);
    try {
      if(section==='Product Discovery') {
        if(minPrice&&maxPrice&&Number(minPrice)>Number(maxPrice))throw new Error('Minimum price must not exceed maximum price.');
        const params=new URLSearchParams({q:query});if(category)params.set('category',category);if(available)params.set('available','true');
        if(minPrice)params.set('min_price',minPrice);if(maxPrice)params.set('max_price',maxPrice);
        await loadCatalog(1,params.toString());
      } else {
        if(!query.trim())throw new Error('Enter a shopping request.');
        const payload={query:query.trim(),channel,customer_id:customer||null,available_only:true,limit:5};
        if(section==='AI Shopping Assistant')setResult(await api<Result>('rag/search',payload));
        if(section==='Recommendations')setResult(await api<Result>('recommendations',{...payload,mode:'context_aware'}));
        if(section==='Agent Workflow') {
          const run=await api<Workflow>('agents/run',{...payload,mode:'context_aware',retrieval_strategy:'auto'});setWorkflow(run);setResult(run.output);
        }
        if(section!=='AI Shopping Assistant')setHistory((await api<Page<History>>('recommendations?limit=20')).items);
      }
    } catch(e) {setError(e instanceof Error?e.message:'Request failed.');} finally {setBusy(false);}
  }
  async function openSaved(id:number) {
    setBusy(true);setError('');setResult(null);
    try {setResult(await api<Result>('recommendations/'+id));} catch(e) {setError(e instanceof Error?e.message:'History unavailable.');} finally {setBusy(false);}
  }
  const title=section==='Dashboard'?'Discover Products Smarter with AI':section;
  const saving=['Recommendations','Agent Workflow'].includes(section);
  return <div className="workspace">
    <aside><a className="brand" href="/"><span>Cc</span><div>Context Cart<small>RETAILRAG AI</small></div></a><p className="nav-label">SHOPPING WORKSPACE</p>
      <nav aria-label="Main navigation">{SECTIONS.map((s,i)=><button key={s} aria-current={section===s?'page':undefined} onClick={()=>{setSection(s);setError('');setResult(null);setWorkflow(null);}}><span className="nav-number">0{i+1}</span>{s}</button>)}</nav>
      <div className="research"><strong>Full research workspace</strong><p>The existing Streamlit application retains catalog editing, tools, customer context, comparison, inventory and simulation.</p>
        {streamlitUrl?<a href={streamlitUrl} target="_blank" rel="noreferrer">Open Streamlit ↗</a>:<small>Set STREAMLIT_APP_URL after separate hosting.</small>}</div>
      <small className="sidebar-footer">Synthetic catalog. Real application records.</small>
    </aside>
    <main><header><span className="eyebrow">CONTEXT CART / INTELLIGENT SHOPPING</span><span className="connection">{connected?(demoMode?'● Read-only cloud demo':'● Backend connected'):'○ Backend not verified'}</span></header>
      <h1>{title}</h1><p className="subtitle">Context-aware recommendations, grounded in product evidence.</p>
      {demoMode&&<p className="note">Free cloud demo: an expanded synthetic catalog, local keyword evidence search, and sample activity. No external AI keys. Full Chroma RAG, document upload, LangGraph and saved records run in the local application.</p>}
      {error&&<div className="alert" role="alert">{error}</div>}{busy&&<p className="loading" role="status">Loading application data…</p>}
      {section==='Dashboard'&&<>
        <div className="metrics">{[['Products',overview?.totals.products],['Customers',overview?.totals.customers],['Recommendations',overview?.totals.recommendations],['Shopping interactions',overview?.totals.interactions]].map(([name,value])=><div key={name}><small>{name}</small><strong>{value??'—'}</strong></div>)}</div>
        <section className="hero"><span className="eyebrow">FIND YOUR NEXT GREAT MATCH</span><h2>A little context goes a long way.</h2><p>Tell us what you need, your budget, and what matters most. Discover products with traceable explanations.</p><button className="primary" onClick={()=>setSection('AI Shopping Assistant')}>Explore with AI →</button></section>
        <div className="columns"><section className="panel"><h2>Channel activity</h2>{overview?.channel_activity.map(row=><div className="activity" key={row.channel}><span>{row.channel}</span><progress value={row.interactions} max={Math.max(...overview.channel_activity.map(r=>r.interactions),1)}/><b>{row.interactions}</b></div>)}{!overview&&<p>Connect the backend to load recorded analytics.</p>}</section>
          <section className="panel"><h2>Popular categories</h2>{overview?.popular_categories.map(row=><div className="activity" key={row.category}><span>{row.category}</span><b>{row.count} events</b></div>)}<small>Counts reflect synthetic shopping events, not attributed sales.</small></section></div>
        <h2>Explore the catalog</h2><div className="product-grid">{products.slice(0,3).map(p=><ProductCard key={p.id} product={p} photo={photos[p.id]}/>)}</div>
      </>}
      {['Product Discovery','AI Shopping Assistant','Recommendations','Agent Workflow'].includes(section)&&<>
        <form className="panel" onSubmit={submit}><label>{section==='Product Discovery'?'Search the catalog':'Your shopping request'}<input value={query} maxLength={section==='Product Discovery'?200:2000} onChange={e=>setQuery(e.target.value)} placeholder="Wireless headphones under INR 3000"/></label>
          <div className="form-row">{section==='Product Discovery'?<><label>Category<select value={category} onChange={e=>setCategory(e.target.value)}><option value="">All categories</option>{Object.keys(photos).length>0&&[...new Set(Object.values(photos).map(p=>p.category))].sort().map(c=><option key={c}>{c}</option>)}</select></label><label className="check"><input type="checkbox" checked={available} onChange={e=>setAvailable(e.target.checked)}/>In stock only</label></>:<><label>Customer<select value={customer} onChange={e=>setCustomer(e.target.value)}><option value="">Guest shopper</option>{customers.map(c=><option key={c.id} value={c.id}>{c.name} ({c.id})</option>)}</select></label><label>Channel<select value={channel} onChange={e=>setChannel(e.target.value)}>{['ecommerce','mobile','store'].map(c=><option key={c}>{c}</option>)}</select></label></>}</div>
          {saving&&!generationEnabled&&<p className="note">Saved generation is disabled in this preparation build. Enable it only after configuring deployment access controls. Existing records remain readable.</p>}
          {section==='Product Discovery'&&<div className="form-row"><label>Minimum price (INR)<input type="number" min="0" step="1" value={minPrice} onChange={e=>setMinPrice(e.target.value)} placeholder="No minimum"/></label><label>Maximum price (INR)<input type="number" min="0" step="1" value={maxPrice} onChange={e=>setMaxPrice(e.target.value)} placeholder="No maximum"/></label></div>}
          <button className="primary" disabled={busy||(saving&&!generationEnabled)}>{section==='Product Discovery'?'Search products':section==='AI Shopping Assistant'?'Retrieve product evidence':section==='Agent Workflow'?'Run existing LangGraph workflow':'Generate & save recommendations'}</button>
          {section==='Product Discovery'&&<small>Keyword search. Use the AI Shopping Assistant for natural-language constraints.</small>}
          {saving&&<small>Creates a saved record. After a timeout, check history before retrying.</small>}
        </form>
        {section==='AI Shopping Assistant'&&<p className="note">{demoMode?'Searches bundled product descriptions locally using word matching and budget filters. No cloud AI or conversational memory.':'Uses the existing RAG search endpoint. No dedicated chat API or conversational memory is implied. Index synchronization remains in Streamlit.'}</p>}
      </>}
      {section==='Product Discovery'&&<><p>{totalProducts} matching products · {products.length?((page-1)*9+1):0}–{Math.min(page*9,totalProducts)} shown</p><div className="product-grid">{products.map(p=><ProductCard key={p.id} product={p} photo={photos[p.id]}/>)}</div>{!products.length&&!busy&&<p className="panel">No matching products. Try fewer keywords or adjust the filters.</p>}<div className="pagination"><button disabled={busy||page===1} onClick={()=>browse(page-1)}>Previous</button><span>Page {page} of {Math.max(1,Math.ceil(totalProducts/9))}</span><button disabled={busy||page*9>=totalProducts} onClick={()=>browse(page+1)}>Next</button></div></>}
      {section==='Recommendation History'&&<section className="panel"><h2>Latest saved recommendations</h2><p>Opening a record is read-only. Showing up to 20 recent records.</p>{!history.length&&<p>No saved recommendations loaded.</p>}<div className="history">{history.map(r=><button key={r.id} disabled={busy} onClick={()=>openSaved(r.id)}><strong>#{r.id} · {r.query||'Personalized request'}</strong><small>{r.customer_id||'Guest'} · {r.channel} · {r.item_count} products · {new Date(r.created_at).toLocaleDateString()}</small></button>)}</div></section>}
      {workflow&&<section className="panel"><h2>Workflow {workflow.status}</h2><small>{workflow.run_id}</small>{workflow.error&&<p role="alert">{workflow.error}</p>}<div className="trace">{workflow.steps.map((s,i)=><div key={i}><strong>{s.agent}</strong><span>{s.status} · {s.duration_ms??'—'} ms</span></div>)}</div></section>}
      {result&&<section><h2>{result.id?`Saved recommendation #${result.id}`:'Product evidence'}</h2><p className="panel">{result.answer||result.message}</p>{result.generation&&<p className="note">{result.generation} · LLM used: {String(result.llm_used)}</p>}{result.warnings?.map(w=><p key={w} className="note">{w}</p>)}{!result.items.length&&<p>No matching products returned.</p>}<div className="product-grid">{result.items.map(i=><ProductCard key={i.product.id} product={i.product} item={i} photo={photos[i.product.id]}/>)}</div><details><summary>Returned evidence and preference context</summary><pre>{JSON.stringify(result,null,2)}</pre></details></section>}
      <footer>Prepared for separate frontend/backend hosting. Product photos are representative stock photography for fictional brands. <a href="/product_images/CREDITS.md">Photo credits</a></footer>
    </main>
  </div>;
}
