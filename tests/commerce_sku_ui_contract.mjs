// Test the browser's actual SKU normalization source in isolation, without DOM mocks.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source=fs.readFileSync(new URL("../products/commerce/storefront.html",import.meta.url),"utf8");
const script=source.match(/<script nonce="__NONCE__">([\s\S]*?)<\/script>/)?.[1];
assert.ok(script,"storefront script is present");
new vm.Script(script,{filename:"storefront.inline.js"});
const start=script.indexOf("const SKU_PATTERN=");
const end=script.indexOf("let skuEditedByMerchant",start);
assert.ok(start>=0&&end>start,"SKU helpers must exist");
const scope=vm.createContext({});
vm.runInContext(script.slice(start,end)+"\nthis.sku=skuFromProductName;\nthis.valid=SKU_PATTERN.test.bind(SKU_PATTERN);",scope);
const expected=[
  ["Stok Alarm","stok-alarm"],
  ["Teklif Ustası","teklif-ustasi"],
  ["Kasa Özet","kasa-ozet"],
  ["Çılgın Ürün 2026","cilgin-urun-2026"],
  ["İstanbul'a Özel","istanbul-a-ozel"],
  ["2026 ürünleri","urun-2026-urunleri"],
  ["!!!","urun"],
  ["A","urun"],
  ["Stok   Alarm   XL","stok-alarm-xl"],
  ["Ürün #@? ₺","urun"]
];
for(const [name,expectedSlug] of expected){
  const result=scope.sku(name);
  assert.equal(result,expectedSlug,"bad SKU normalization for "+name);
  assert.ok(scope.valid(result),"SKU is backend invalid for "+name);
}
const long="A".repeat(100);
assert.equal(scope.sku(long).length,32);
assert.ok(scope.valid(scope.sku(long)));
const required=[
  'name="sku"','name="name"','fillSkuFromName','humanProductError',
  'skuEditedByMerchant','product.sku','Kaydedilemedi: ',
  'stok-alarm','elements.name.addEventListener("input",fillSkuFromName)',
  'elements.sku.addEventListener("invalid"'
];
for(const item of required)assert.ok(source.includes(item),"missing UX contract: "+item);
console.log("SKU validation: 10 localized names, input validation, UI bindings and JavaScript parsing passed.");
