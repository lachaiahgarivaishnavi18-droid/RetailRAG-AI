const STOP=new Set(['a','an','the','for','under','below','above','over','up','to','inr','rs','with','and','what','which','is','are','me','show','find','please','i','want','need']);
const aliases={backpacks:'backpack',rucksack:'backpack',rucksacks:'backpack',headphones:'headphone',headsets:'headphone',speakers:'speaker',bags:'bag',laptops:'laptop',notebooks:'laptop',smartphones:'smartphone',phones:'phone',smartwatches:'smartwatch',accessories:'accessory',shoes:'shoe',sneakers:'sneaker'};
export const terms=text=>(String(text).toLowerCase().replace(/cross[- ]body/g,'crossbody').match(/[a-z0-9]+/g)||[]).map(w=>aliases[w]||w);
export function queryFilters(query='') {
 const maximum=query.match(/(?:under|below|up to)\s*(?:inr|rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)/i);
 const minimum=query.match(/(?:above|over)\s*(?:inr|rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)/i);
 const cleaned=query.replace(/(?:under|below|up to|above|over)\s*(?:inr|rs\.?|₹)?\s*[\d,]+(?:\.\d+)?/gi,'');
 return {words:[...new Set(terms(cleaned).filter(w=>!STOP.has(w)))],min:minimum?Number(minimum[1].replaceAll(',','')):0,max:maximum?Number(maximum[1].replaceAll(',','')):Infinity};
}
export function searchCatalog(products,{query='',category='',brand='',available=false,min,max}={}) {
 const parsed=queryFilters(query);const lower=min===undefined?parsed.min:Number(min),upper=max===undefined?parsed.max:Number(max);
 const has=word=>parsed.words.includes(word);
 const intent=has('backpack')||has('crossbody')||has('bag')||has('accessory')?'Accessories':has('laptop')?'Laptops':has('smartphone')||has('phone')?'Smartphones':has('smartwatch')?'Smartwatches':has('speaker')?'Bluetooth Speakers':undefined;
 return products.filter(p=>(!intent||p.category===intent)&&(!category||p.category.toLowerCase()===category.toLowerCase())&&(!brand||p.brand.toLowerCase()===brand.toLowerCase())&&(!available||p.available)&&Number(p.price)>=lower&&Number(p.price)<=upper).map(p=>{
  const primary=new Set(terms(p.name+' '+(p.product_type||'')+' '+p.category));
  const all=new Set(terms([p.name,p.description,p.category,p.brand,...p.features].join(' ')));
  // All meaningful query terms must match; "laptop backpack" cannot return a laptop.
  if(!parsed.words.every(w=>all.has(w)))return null;
  const score=parsed.words.length?parsed.words.reduce((sum,w)=>sum+(primary.has(w)?2:1),0)/(parsed.words.length*2):1;
  return {product:p,score};
 }).filter(Boolean).sort((a,b)=>b.score-a.score||b.product.rating-a.product.rating||Number(a.product.price)-Number(b.product.price)||a.product.id.localeCompare(b.product.id));
}
