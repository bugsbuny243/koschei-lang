// Tests the real in-page IndexedDB workspace implementation without packages.
// An event-driven in-memory fake intentionally follows IDB request/transaction
// event ordering (request onsuccess before transaction oncomplete).
import fs from "node:fs";
import vm from "node:vm";
import {webcrypto} from "node:crypto";
import assert from "node:assert/strict";

const html=fs.readFileSync(new URL("../commercial/lang-site/business-tools.html",import.meta.url),"utf8");
const script=html.match(/<script>([\s\S]*?)<\/script>/i)?.[1];
assert.ok(script);
new vm.Script(script,{filename:"business-tools.inline.js"});
const extract=(start,end)=>{
  const i=script.indexOf(start),j=script.indexOf(end,i+start.length);
  assert.ok(i!==-1&&j>i,"missing source range "+start+" -> "+end);
  return script.slice(i,j);
};
const validation=extract("  function validateSavedProject(doc){","  function restoreProject(doc){");
const storage=extract("  /* DEVICE WORKSPACE STORAGE:","  /* END DEVICE WORKSPACE STORAGE */")
              +"  /* END DEVICE WORKSPACE STORAGE */";

function fakeIdb(){
  const memory=new Map();
  let created=false;
  const db={
    objectStoreNames:{contains:()=>created},
    createObjectStore(name,opts){assert.equal(name,"projects");assert.equal(opts.keyPath,"id");created=true;},
    close(){},
    transaction(name,mode){
      assert.equal(name,"projects");
      assert.ok(mode==="readwrite"||mode==="readonly");
      const tx={oncomplete:null,onabort:null,onerror:null};
      const queue=fn=>{
        const req={result:undefined,onsuccess:null,onerror:null};
        queueMicrotask(()=>{
          try{req.result=fn();req.onsuccess?.();queueMicrotask(()=>tx.oncomplete?.());}
          catch(e){req.error=e;req.onerror?.();queueMicrotask(()=>tx.onabort?.());}
        });
        return req;
      };
      tx.objectStore=(store)=>{
        assert.equal(store,"projects");
        return {
          getAll:()=>queue(()=>Array.from(memory.values())),
          get:id=>queue(()=>memory.get(id)),
          put:rec=>queue(()=>{memory.set(rec.id,rec);return rec.id;}),
          delete:id=>queue(()=>{memory.delete(id);return undefined;})
        };
      };
      return tx;
    }
  };
  return {
    memory,
    open(name,version){
      assert.equal(name,"koschei-business-device/v1");
      assert.equal(version,1);
      const request={result:db,onupgradeneeded:null,onsuccess:null,onerror:null,onblocked:null};
      queueMicrotask(()=>{
        if(!created)request.onupgradeneeded?.();
        request.onsuccess?.();
      });
      return request;
    }
  };
}
const idb=fakeIdb(),sandbox=vm.createContext({
  window:{indexedDB:idb},
  indexedDB:idb,
  crypto:webcrypto,
  console
});
vm.runInContext([
  'const PROJECT_SCHEMA="koschei.business-tools/project/v1";',
  'const savedCurrencies=["TRY","USD","EUR"];',
  'const maxRows={quote:24,stock:40,cash:40};',
  'const moneyPattern=/^(?:0|[1-9]\\d{0,8})(?:\\.\\d{1,2})?$/;',
  validation,
  storage,
  "this.api={workspaceAll,workspaceRead,workspaceWrite,workspaceRemove,workspaceNewRecord,workspaceDisplayName,workspaceValidateRecord,workspaceOpenDb};"
].join("\n"),sandbox);
const api=sandbox.api;
const quote={
  schema:"koschei.business-tools/project/v1",tool:"quote",currency:"TRY",
  names:["Tasarım"],payload:{kind:"quote",vat:20,discount:5,items:[{quantity:2,price:"100.00"}]},
  details:{title:"Kasım teklifi",company:"A",customer:"B",reference:"TK-11",date:"2026-11-16"}
};
const cash={
  schema:quote.schema,tool:"cash",currency:"EUR",
  names:["Ödeme"],payload:{kind:"cash",opening:"1.00",items:[{type:"income",amount:"5.00"}]}
};
assert.equal((await api.workspaceAll()).length,0);
const q=api.workspaceNewRecord(quote," Teklif 1 ");
const c=api.workspaceNewRecord(cash,"Kasa raporu");
assert.match(q.id,/^[a-f0-9]{32}$/);
assert.notEqual(q.id,c.id);
assert.equal(q.name,"Teklif 1");
await api.workspaceWrite(q);
await api.workspaceWrite(c);
assert.equal((await api.workspaceAll()).length,2);
assert.equal((await api.workspaceRead(q.id)).name,"Teklif 1");
await api.workspaceWrite({...q,name:"Teklif güncellendi"});
assert.equal((await api.workspaceRead(q.id)).name,"Teklif güncellendi");
await api.workspaceRemove(c.id);
assert.equal((await api.workspaceAll()).length,1);
assert.equal(idb.memory.size,1);
await assert.rejects(api.workspaceRead(c.id),/bulunamadı/i);
await assert.rejects(api.workspaceRead("__proto__"),/kimliği/);
assert.throws(()=>api.workspaceNewRecord({...quote,tool:"invalid"},"Bad"),/./);
assert.throws(()=>api.workspaceNewRecord(quote,""),/Kayıt adı/);
assert.throws(()=>api.workspaceDisplayName("a".repeat(81)),/80/);
assert.equal(api.workspaceDisplayName("\u202eKayıt\u202c"),"Kayıt");
assert.throws(()=>api.workspaceValidateRecord({...q,doc:{...quote,tool:"stock"}}),/./);
assert.throws(()=>api.workspaceValidateRecord({...q,doc:{...quote,names:["x","y"]}}),/./);
assert.throws(()=>api.workspaceValidateRecord({...q,id:"not-a-random-id"}),/./);
idb.memory.set("corrupt",{...q,id:"corrupt",name:"BAD"});
assert.equal((await api.workspaceAll()).length,1,"corrupt entry hidden, good data preserved");
// Simulate Android webview with storage unavailable: always surface JSON fallback.
const unavailable=vm.createContext({
  window:{},
  crypto:webcrypto,
});
vm.runInContext([
  'const PROJECT_SCHEMA="koschei.business-tools/project/v1";',
  'const savedCurrencies=["TRY","USD","EUR"];',
  'const maxRows={quote:24,stock:40,cash:40};',
  'const moneyPattern=/^(?:0|[1-9]\\d{0,8})(?:\\.\\d{1,2})?$/;',
  validation,storage,
  "this.open=workspaceOpenDb;"
].join("\n"),unavailable);
await assert.rejects(unavailable.open(),/JSON yedeğini kullan/);
for(const required of [
  'id="save-device"',
  'id="toggle-workspace"',
  'id="workspace-panel"',
  'id="workspace-feedback"',
  'id="workspace-list"',
  'void workspaceSave()',
  'workspaceOpen(record)',
  'workspaceRename(record)',
  'workspaceDelete(record)',
  'role="status"',
  "textContent=record.name",
  "window.confirm("
]) assert.ok(html.includes(required),required);
assert.ok(!html.includes("localStorage"));
assert.ok(!html.includes("sessionStorage"));
assert.ok(!html.includes('fetch("/api/business/workspace'));
console.log("IndexedDB workspace checks passed: add/list/read/rename/delete, invalid records, no storage fallback.");
