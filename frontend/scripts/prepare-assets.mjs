import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = path.resolve(frontend, '../assets/product_images');
const manifest = JSON.parse(await readFile(path.join(source, 'manifest.json'), 'utf8'));
const output = {};
for (const [id, record] of Object.entries(manifest.products)) {
  const file = path.resolve(source, record.file);
  if (!file.startsWith(source + path.sep)) throw new Error('Invalid photo path');
  const bytes = await readFile(file);
  if (createHash('sha256').update(bytes).digest('hex') !== record.sha256) throw new Error(`Photo integrity failed: ${id}`);
  const destination = path.join(frontend, 'public/product_images', record.file);
  await mkdir(path.dirname(destination), { recursive: true });
  await copyFile(file, destination);
  output[id] = { name: record.name, category: record.category, description: record.description,
    src: '/product_images/' + record.file, alt: record.name + ' - representative stock photograph', photographer: record.photographer,
    source_url: record.source_url, license_url: record.license_url };
}
await writeFile(path.join(frontend, 'public/product-photos.json'), JSON.stringify(output));
await copyFile(path.join(source, 'CREDITS.md'), path.join(frontend, 'public/product_images/CREDITS.md'));
console.log(`Prepared ${Object.keys(output).length} verified local product photos; originals unchanged.`);
