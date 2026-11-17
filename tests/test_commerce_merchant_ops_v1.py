"""Merchant CSV import, stock audit and consistent SQLite backup integration tests."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from http.server import ThreadingHTTPServer
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]/"products"/"commerce"
sys.path.insert(0,str(ROOT))
from catalog_csv import MAX_CSV_BYTES, parse_product_csv
from storage import CommerceError,CommerceStore
from server import Config,make_handler

ORIGIN="https://merchant.example.test"
PASSWORD="test-only-private-long-admin-password"
HEADER="sku;name;category;description;price_try;stock;active\n"


def csv_blob(*rows: str, bom: bool = False) -> bytes:
    value=HEADER+"".join(row+"\n" for row in rows)
    return (b"\xef\xbb\xbf" if bom else b"")+value.encode("utf-8")


def product(sku="stok-alarm",stock=5):
    return {"sku":sku,"name":"Stok Alarm","category":"Yazılım",
            "description":"Yerel stok kontrolü","price_cents":280000,
            "stock":stock,"active":True}


class CommerceMerchantOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path=Path(self.tmp.name)/"commerce.db"
        self.store=CommerceStore(self.db_path)
        server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(
            self.store,Config(ORIGIN,PASSWORD,"Test Commerce",False)
        ))
        self.server=server
        self.base=f"http://127.0.0.1:{server.server_port}"
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(timeout=3)))

    def request(self,path,method="GET",body=None,ctype=None,cookie=None,origin=ORIGIN):
        headers={}
        if ctype:headers["Content-Type"]=ctype
        if cookie:headers["Cookie"]=cookie
        if origin is not None:headers["Origin"]=origin
        req=Request(self.base+path,method=method,data=body,headers=headers)
        try:
            with urlopen(req,timeout=20) as response:
                return response.status,response.read(),response.headers
        except HTTPError as exc:
            return exc.code,exc.read(),exc.headers

    def login(self):
        status,data,headers=self.request("/api/admin/login","POST",
            json.dumps({"password":PASSWORD}).encode(),"application/json")
        self.assertEqual(status,200,data)
        return headers["Set-Cookie"].split(";",1)[0]

    def test_csv_utf8_bom_quoted_semicolon_and_local_prices(self):
        data=csv_blob(
            'stok-alarm;Stok Alarm;Yazılım;"Tırnak içinde; noktalı virgül";2800,50;10000;1',
            "kasa-ozet;Kasa Özet;Yazılım;Kasa özeti;19;0;0",bom=True
        )
        rows=parse_product_csv(data)
        self.assertEqual(rows[0]["price_cents"],280050)
        self.assertEqual(rows[0]["stock"],10000)
        self.assertEqual(rows[0]["description"],"Tırnak içinde; noktalı virgül")
        self.assertEqual(rows[1]["price_cents"],1900)
        self.assertEqual(rows[1]["active"],0)
        self.assertEqual(self.store.bulk_create_products(rows,True)["count"],2)
        self.assertEqual(self.store.products(),[])
        result=self.store.bulk_create_products(rows,False)
        self.assertEqual(result["created"],2)
        self.assertEqual(len(self.store.products(public=False)),2)
        self.assertEqual(len(self.store.products()),1)
        movements=self.store.stock_history()
        self.assertEqual(len(movements),2)
        self.assertTrue(all(x["reason"]=="import" for x in movements))
        self.assertEqual({x["sku"]:x["stock_after"] for x in movements},
                         {"stok-alarm":10000,"kasa-ozet":0})

    def test_invalid_csv_rejected_before_any_insert(self):
        failures=[
            (b"hello","csv_header_invalid"),
            (b"\xff"+csv_blob("item-1;A;B;C;3;1;1"),"csv_encoding_invalid"),
            (csv_blob("item-1;A;B;C;3;1"),"csv_row_columns_invalid"),
            (csv_blob("item-1;A;B;C;=1+2;1;1"),"csv_price_invalid"),
            (csv_blob("item-1;A;B;C;10;100001;1"),"csv_stock_invalid"),
            (csv_blob("item-1;A;B;C;10;1;yes"),"csv_active_invalid"),
            (csv_blob("Ürün 1;A;B;C;10;1;1"),"invalid_sku"),
            (csv_blob("item-1;A;B;C;10;1;1","item-1;Again;B;C;10;1;1"),"import_duplicate_sku"),
            (csv_blob(*[f"item-{i:03d};A;B;C;10;1;1" for i in range(101)]),"csv_row_limit"),
            (b"A"*(MAX_CSV_BYTES+1),"csv_size_invalid"),
            (csv_blob("item-1;A;B;C;0;1;1"),"csv_price_invalid"),
        ]
        for content,expected in failures:
            with self.subTest(expected=expected):
                with self.assertRaises(CommerceError) as exc:
                    parse_product_csv(content)
                self.assertEqual(exc.exception.code,expected)
        self.assertEqual(self.store.products(public=False),[])
        self.assertEqual(self.store.stock_history(),[])

    def test_existing_sku_blocks_whole_file_and_stock_changes(self):
        self.store.set_product(product(stock=17))
        before=self.store.products(public=False)
        history=self.store.stock_history()
        rows=parse_product_csv(csv_blob(
            "new-one;New product;Other;New;2.50;3;1",
            "stok-alarm;Overwrite attempt;Other;Bad;1;0;1",
        ))
        for dry in (True,False):
            with self.assertRaises(CommerceError) as err:
                self.store.bulk_create_products(rows,dry)
            self.assertEqual(err.exception.code,"import_sku_exists")
        self.assertEqual(self.store.products(public=False),before)
        self.assertEqual(self.store.stock_history(),history)

    def test_stock_manual_edit_audit_and_order_accept_cancel(self):
        self.store.set_product(product(stock=5))
        self.assertEqual(self.store.stock_history()[0]["reason"],"created")
        updated=product(stock=8)
        self.store.set_product(updated,sku="stok-alarm")
        self.assertEqual(self.store.stock_history()[0]["delta"],3)
        self.assertEqual(self.store.stock_history()[0]["stock_after"],8)
        self.store.set_product(updated,sku="stok-alarm")
        self.assertEqual(len(self.store.stock_history()),2,"no phantom movement for unchanged count")
        order=self.store.create_order({
            "idempotency_key":"b"*32,
            "customer":{"name":"Guest","email":"guest@example.test","note":""},
            "items":[{"sku":"stok-alarm","quantity":2}]
        })
        oid=order["id"]
        self.assertEqual(len(self.store.stock_history()),2,"pending orders do not move stock")
        self.store.change_order(oid,"accept")
        self.assertEqual(self.store.stock_history()[0]["reason"],"order_accept")
        self.assertEqual(self.store.stock_history()[0]["delta"],-2)
        self.assertEqual(self.store.stock_history()[0]["stock_after"],6)
        self.store.change_order(oid,"cancel")
        self.assertEqual(self.store.stock_history()[0]["reason"],"order_cancel")
        self.assertEqual(self.store.stock_history()[0]["delta"],2)
        self.assertEqual(self.store.stock_history()[0]["stock_after"],8)
        self.assertEqual(self.store.stock_history()[0]["order_id"],oid)
        with self.assertRaises(CommerceError):
            self.store.change_order(oid,"accept")
        self.assertEqual(len(self.store.stock_history()),4)

    def test_online_backup_session_stripped_and_original_untouched(self):
        self.store.set_product(product())
        token=self.store.login_session()
        self.assertTrue(self.store.is_admin(token))
        with self.store.backup_copy() as filename:
            self.assertTrue(filename.is_file())
            with sqlite3.connect(filename) as snapshot:
                self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0],0)
                self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM products").fetchone()[0],1)
                self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0],1)
                self.assertEqual(snapshot.execute("PRAGMA quick_check").fetchone()[0],"ok")
                self.assertEqual(snapshot.execute("PRAGMA journal_mode").fetchone()[0],"delete")
            self.assertFalse(filename.with_name(filename.name+"-wal").exists())
        self.assertFalse(filename.exists(),"temporary backup file must be cleaned up")
        self.assertTrue(self.store.is_admin(token),"live login stays valid")

    def test_http_auth_preview_commit_history_and_binary_backup(self):
        data=csv_blob("new-one;Kahve;Gıda;Kahve;150.99;12;1",bom=True)
        url="/api/admin/products/import"
        self.assertEqual(self.request(url+"?dry_run=1","POST",data,"text/csv")[0],401)
        cookie=self.login()
        self.assertEqual(self.request(url+"?dry_run=1","POST",data,"text/csv",cookie,
                                      origin="https://attacker.example")[0],403)
        self.assertEqual(self.request(url+"?dry_run=1","POST",data,"application/json",cookie)[0],415)
        status,raw,_=self.request(url+"?dry_run=1","POST",data,"text/csv",cookie)
        preview=json.loads(raw)
        self.assertEqual(status,200,preview)
        self.assertEqual(preview["count"],1)
        self.assertTrue(preview["dry_run"])
        self.assertEqual(len(self.store.products()),0)
        status,raw,_=self.request(url,"POST",data,"text/csv",cookie)
        self.assertEqual(status,200,raw)
        self.assertEqual(json.loads(raw)["created"],1)
        self.assertEqual(self.request(url,"POST",data,"text/csv",cookie)[0],409)
        self.assertEqual(self.request("/api/admin/stock-movements")[0],401)
        status,raw,_=self.request("/api/admin/stock-movements",cookie=cookie)
        self.assertEqual(status,200,raw)
        self.assertEqual(json.loads(raw)["movements"][0]["sku"],"new-one")
        self.assertEqual(self.request("/api/admin/stock-movements?sku=bad!code",cookie=cookie)[0],400)
        self.assertEqual(self.request("/api/admin/backup","POST",b"{}","application/json")[0],401)
        self.assertEqual(self.request("/api/admin/backup","POST",b"{}","application/json",cookie,
                                      origin="https://attacker.example")[0],403)
        status,body,headers=self.request("/api/admin/backup","POST",b"{}","application/json",cookie)
        self.assertEqual(status,200,body[:400])
        self.assertTrue(body.startswith(b"SQLite format 3\x00"))
        self.assertIn("attachment;",headers["Content-Disposition"])
        self.assertIn("no-store",headers["Cache-Control"])
        path=Path(self.tmp.name)/"roundtrip.sqlite3"
        path.write_bytes(body)
        with sqlite3.connect(path) as restored:
            self.assertEqual(restored.execute("SELECT COUNT(*) FROM products").fetchone()[0],1)
            self.assertEqual(restored.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0],0)
            self.assertEqual(restored.execute("PRAGMA quick_check").fetchone()[0],"ok")

    def test_ui_contract(self):
        site=(ROOT/"storefront.html").read_text(encoding="utf-8")
        for token in (
            'id="import-file"','id="preview-csv"','id="commit-csv"',
            'id="download-csv-template"','id="stock-history"',
            'id="download-db-backup"','id="backup-message"',
            "function drawStockHistory()","async function uploadCsv(dry)",
            "async function backupDatabase()","state.importReady",
            "URL.createObjectURL","window", "merchant-ops",
        ):
            if token=="window": continue
            self.assertIn(token,site)
        self.assertNotIn('style="',site)
        self.assertNotIn("localStorage",site)


if __name__=="__main__":
    unittest.main()
