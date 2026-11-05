# Expanded synthetic catalog

The deployable source of truth is `lib/demo-data.json`, not a displayed count.
It contains 244 complete product rows: the original 24 records (unchanged) plus
220 new fictional products. No local customer/recommendation database is migrated
or reseeded by this frontend expansion.

| Category | Products |
|---|---:|
| Electronics | 20 |
| Accessories | 64 |
| Bluetooth Speakers | 20 |
| Smartphones | 20 |
| Laptops | 20 |
| Smartwatches | 20 |
| Apparel | 20 |
| Footwear | 20 |
| Home | 20 |
| Sports | 20 |

Accessories includes 20 new laptop backpacks, 20 crossbody bags, 20 travel bags,
and the four retained accessories. Photographs are representative stock photos
for fictional products; brands and specifications are synthetic. Each product
has a different source photograph and verified SHA-256. New photos are local
under `assets/product_images/expanded/`; sources and license links are recorded
in the identity-guarded manifest and `CREDITS.md`. Premium Unsplash images are
excluded. No image key, hosted model or external service is required at runtime.

Search normalizes plurals and cross-body spelling, requires all meaningful words,
and distinguishes laptop intent from laptop-backpack intent. Unknown requests
return an honest empty result rather than unrelated products. Price and category
constraints compose with availability and natural-language budget constraints.

GET `/api/backend/products` paginates with `limit` (1–100, default 9) and `offset`.
All filtering happens before pagination; `total` is the actual matched row count.
The UI requests nine cards per page, retains submitted filters when paging, and
uses the existing three-column desktop, two-column tablet, one-column mobile grid.
Explicit price inputs are in Product Discovery. Full Python services remain
available locally; configuring BACKEND_API_URL retains the real backend path.

`tests/catalog.test.mjs` checks all categories and requested query families,
record/photo uniqueness and identity, composable filters, invalid inputs, and a
complete traversal of all 244 products without missing or duplicate IDs.
