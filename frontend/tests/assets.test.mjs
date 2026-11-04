import {test} from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

test('frontend photo preparation verifies all 24 assets without modifying originals',async()=>{
  const source=new URL('../../assets/product_images/manifest.json',import.meta.url);
  const before=await readFile(source);
  execFileSync(process.execPath,['scripts/prepare-assets.mjs']);
  assert.deepEqual(await readFile(source),before);
  const original=JSON.parse(before);
  const prepared=JSON.parse(await readFile(new URL('../public/product-photos.json',import.meta.url),'utf8'));
  assert.equal(Object.keys(prepared).length,24);
  for(const [id,photo] of Object.entries(prepared)){
    assert.equal(photo.name,original.products[id].name);
    assert.equal(photo.alt,photo.name+' - representative stock photograph');
    const bytes=await readFile(new URL('../public'+photo.src,import.meta.url));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),original.products[id].sha256);
  }
});
