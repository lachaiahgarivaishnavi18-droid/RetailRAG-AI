import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import data from '../lib/demo-data.json' with {type:'json'};
import {demoResponse} from '../lib/demo.mjs';
import {searchCatalog} from '../lib/catalog-search.mjs';
const get=async params=>{
 const response=await demoResponse(new Request('https://demo.example/api/backend/products?'+new URLSearchParams(params)),['products']);
 assert.equal(response.status,200);return response.json();
};
test('real persisted rows have unique identities, descriptions and category-matched unique local photos',async()=>{
 assert.equal(data.products.length,244);
 for(const field of ['id','name','description'])assert.equal(new Set(data.products.map(p=>p[field])).size,244,field);
 const manifest=JSON.parse(await readFile(new URL('../../assets/product_images/manifest.json',import.meta.url),'utf8')).products;
 const hashes=[];
 for(const p of data.products){
  assert.ok(Number(p.price)>0&&p.rating>=0&&p.rating<=5&&p.stock_quantity>=0);
  assert.equal(p.available,p.stock_quantity>0);assert.ok(p.features.length);
  const photo=manifest[p.id];assert.ok(photo,p.id);assert.equal(photo.name,p.name);assert.equal(photo.category,p.category);assert.equal(photo.description,p.description);
  const bytes=await readFile(new URL('../../assets/product_images/'+photo.file,import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),photo.sha256);hashes.push(photo.sha256);
 }
 assert.equal(new Set(hashes).size,244);
});
test('every major category has at least 20 persisted products and exact category filtering',async()=>{
 const categories=[...new Set(data.products.map(p=>p.category))];assert.equal(categories.length,10);
 for(const category of categories){
  const expected=data.products.filter(p=>p.category===category);assert.ok(expected.length>=20,category);
  const page=await get({category,limit:'100'});assert.equal(page.total,expected.length);assert.ok(page.items.every(p=>p.category===category));
 }
});
test('requested searches return multiple relevant products without unrelated categories',()=>{
 for(const [query,category,minimum] of [['laptop backpack','Accessories',20],['crossbody bag','Accessories',20],['travel bag','Accessories',20],['wireless headphones','Electronics',15],['bluetooth speakers','Bluetooth Speakers',20],['smartphones','Smartphones',20],['laptops','Laptops',20],['smartwatches','Smartwatches',20],['accessories','Accessories',20]]){
  const rows=searchCatalog(data.products,{query});assert.ok(rows.length>=minimum,`${query}: ${rows.length}`);assert.ok(rows.every(r=>r.product.category===category),query);
 }
 assert.equal(searchCatalog(data.products,{query:'laptop backpack',category:'Laptops'}).length,0);
 assert.equal(searchCatalog(data.products,{query:'zzqqxxunmatched'}).length,0);
 assert.equal(searchCatalog(data.products,{query:'wireless banana headphones'}).length,0);
 assert.ok(searchCatalog(data.products,{query:'laptop backpacks'}).length>=20);
});
test('price, stock, query and category filters compose, including natural budget',async()=>{
 const filtered=await get({q:'laptop backpack',category:'Accessories',min_price:'1800',max_price:'3500',available:'true',limit:'100'});
 assert.ok(filtered.items.length>1);assert.ok(filtered.items.every(p=>Number(p.price)>=1800&&Number(p.price)<=3500&&p.available));
 const natural=await get({q:'wireless headphones under INR 3000',limit:'100'});assert.ok(natural.total>1);assert.ok(natural.items.every(p=>Number(p.price)<=3000));
 for(const params of [{min_price:'5000',max_price:'1000'},{limit:'101'},{offset:'-1'},{min_price:'bad'}])assert.equal((await demoResponse(new Request('https://demo.example/api/backend/products?'+new URLSearchParams(params)),['products'])).status,422);
});
test('server pagination reaches every row once, preserves query filters and has an empty final page',async()=>{
 const ids=[];let total;
 for(let offset=0;offset<data.products.length;offset+=9){const page=await get({offset:String(offset),limit:'9'});total=page.total;ids.push(...page.items.map(p=>p.id));}
 assert.equal(ids.length,total);assert.equal(new Set(ids).size,244);assert.equal((await get({offset:'9999'})).items.length,0);
 const a=await get({q:'laptop backpack',offset:'0',limit:'9'}),b=await get({q:'laptop backpack',offset:'9',limit:'9'});
 assert.ok(a.items.length===9&&b.items.length===9);assert.equal(a.total,b.total);assert.ok(!a.items.some(p=>b.items.some(other=>other.id===p.id)));
});
