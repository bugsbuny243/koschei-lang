// Browser project integrity tests without extra browser-side dependencies.
import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const html=fs.readFileSync(new URL("../commercial/lang-site/business-tools.html",import.meta.url),"utf8");
const match=html.match(/<script>([\s\S]*?)<\/script>/i);
assert.ok(match,"inline browser controller not found");
const script=match[1];
new vm.Script(script,{filename:"commercial/lang-site/business-tools.html:inline.js"});

function sliceFunction(start,end){
  const a=script.indexOf("function "+start+"(");
  const b=script.indexOf("function "+end+"(",a);
  assert.ok(a>=0&&b>a,"missing function boundary "+start+" "+end);
  return script.slice(a,b);
}
const validatorSrc=sliceFunction("validateSavedProject","restoreProject");
const csvSrc=sliceFunction("csvEscape","downloadCsv");
const sandbox=vm.createContext({});
vm.runInContext([
  'const PROJECT_SCHEMA="koschei.business-tools/project/v1";',
  'const savedCurrencies=["TRY","USD","EUR"];',
  'const maxRows={quote:24,stock:40,cash:40};',
  'const moneyPattern=/^(?:0|[1-9]\\d{0,8})(?:\\.\\d{1,2})?$/;',
  validatorSrc,csvSrc,
  "this.validate=validateSavedProject;",
  "this.csv=csvEscape;"
].join("\n"),sandbox);

const validQuote={
  schema:"koschei.business-tools/project/v1", tool:"quote",currency:"TRY",
  names:["Tasarım"],payload:{kind:"quote",vat:20,discount:5,
    items:[{quantity:2,price:"100.00"}]},
  details:{title:"Fiyat teklifi",company:"Acme",customer:"Müşteri",reference:"TK-1",date:"2026-11-16"}
};
const validStock={
  schema:validQuote.schema,tool:"stock",currency:"EUR",names:["Mürekkep"],
  payload:{kind:"stock",items:[{quantity:1,minimum:3,cost:"50.00"}]}
};
const validCash={
  schema:validQuote.schema,tool:"cash",currency:"USD",names:["Satış"],
  payload:{kind:"cash",opening:"10.00",items:[{type:"income",amount:"20.00"}]}
};
for(const doc of [validQuote,validStock,validCash]){
  assert.equal(sandbox.validate(doc),doc,"valid project must be accepted");
}
const bad=[
  {...validQuote,schema:"evil"},
  {...validQuote,tool:"__proto__"},
  {...validQuote,currency:"BTC"},
  {...validQuote,names:["=1+1","something"]},
  {...validQuote,payload:{...validQuote.payload,discount:101}},
  {...validQuote,payload:{...validQuote.payload,items:[{quantity:-1,price:"100.00"}]}},
  {...validQuote,payload:{...validQuote.payload,items:[{quantity:1,price:"10000000.00"}]}},
  {...validQuote,details:{...validQuote.details,customer:"X".repeat(81)}},
  {...validQuote,details:{...validQuote.details,date:"tomorrow"}},
  {...validStock,payload:{...validStock.payload,items:[{quantity:-1,minimum:3,cost:"50.00"}]}},
  {...validCash,payload:{...validCash.payload,items:[{type:"income",amount:"-10.00"}]}},
  {...validCash,payload:{...validCash.payload,items:[{type:"expense",amount:"0.00"}]}}
];
function ErrorLike(error){return error&&error.name==="Error"&&typeof error.message==="string";}
for(const doc of bad){
  assert.throws(()=>sandbox.validate(doc),ErrorLike,"invalid project must be rejected");
}
assert.equal(sandbox.csv("hello"),'"hello"');
assert.equal(sandbox.csv('he said "ok"'),'"he said ""ok"""');
assert.equal(sandbox.csv("=SUM(A1)"),'"\'=SUM(A1)"');
assert.equal(sandbox.csv("  +9"),'"\'  +9"');
assert.equal(sandbox.csv("@abc"),'"\'@abc"');
assert.ok(html.includes('id="project-file"'));
assert.ok(html.includes('type="file"'));
assert.ok(html.includes("file.size>24576"));
assert.ok(html.includes("restoreProject(JSON.parse(text))"));
assert.ok(html.includes("window.print()"));
assert.ok(html.includes("report-disclaimer"));
assert.ok(!html.includes("localStorage"));
assert.ok(!html.includes("sessionStorage"));
assert.ok(!html.includes("<script src="));
console.log("Browser project JS parsed; 3 valid, 12 invalid, 5 CSV checks passed.");
