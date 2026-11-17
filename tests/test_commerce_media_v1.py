"""Commerce catalog v1.1: photos, categories, SQLite migration, HTTP security."""
from __future__ import annotations

from io import BytesIO
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import sqlite3
import sys
import tempfile
import unittest

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]/"products"/"commerce"
sys.path.insert(0,str(ROOT))
from storage import CommerceError,CommerceStore
from image_codec import normalize_product_photo,MAX_IMAGE
from server import Config,make_handler

ORIGIN="https://shop.example.test"
ADMIN="nonproduction-merchant-long-password"


def product(sku="coffee-1",category="Gıda",name="Kahve"):
    return {"sku":sku,"name":name,"category":category,"description":"Taze kahve",
            "stock":7,"price_cents":1500,"active":True}


def image_source(kind="PNG",note=None):
    img=Image.new("RGB",(1440,960),(14,153,176))
    output=BytesIO()
    if kind=="JPEG":
        exif=Image.Exif()
        exif[270]=note or "secret metadata must not leak"
        img.save(output,format="JPEG",quality=85,exif=exif)
    else:
        img.save(output,format=kind)
    return output.getvalue()


class MediaCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=CommerceStore(Path(self.tmp.name)/"commerce.db")
        handler=make_handler(self.store,Config(ORIGIN,ADMIN,"Merchant Gallery",False))
        self.httpd=ThreadingHTTPServer(("127.0.0.1",0),handler)
        self.base=f"http://127.0.0.1:{self.httpd.server_port}"
        thread=Thread(target=self.httpd.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(lambda:(self.httpd.shutdown(),self.httpd.server_close(),thread.join(timeout=3)))

    def request(self,path,method="GET",body=None,content_type=None,cookie=None,origin=ORIGIN):
        headers={}
        if content_type:headers["Content-Type"]=content_type
        if cookie:headers["Cookie"]=cookie
        if origin is not None:headers["Origin"]=origin
        req=Request(self.base+path,method=method,headers=headers,data=body)
        try:
            with urlopen(req,timeout=12) as r:
                return r.status,r.read(),r.headers
        except HTTPError as e:
            return e.code,e.read(),e.headers

    def login(self):
        status,body,headers=self.request(
            "/api/admin/login","POST",json.dumps({"password":ADMIN}).encode(),"application/json"
        )
        self.assertEqual(status,200,body)
        return headers["Set-Cookie"].split(";",1)[0]

    def test_category_catalog_and_no_placeholder_image(self):
        self.store.set_product(product())
        self.store.set_product(product("lamp-1","Elektronik","Lamba"))
        catalog=self.store.products()
        self.assertEqual({x["category"] for x in catalog},{"Gıda","Elektronik"})
        self.assertFalse(any(x["has_image"] for x in catalog))
        self.assertTrue(all(x["image_version"] is None for x in catalog))
        self.assertEqual(self.store.products(public=False)[0]["category"],"Gıda" if
                         self.store.products(public=False)[0]["sku"]=="coffee-1" else "Elektronik")
        with self.assertRaises(CommerceError):
            self.store.set_product(product("bad-1","A"*49))
        with self.assertRaises(CommerceError):
            self.store.set_product(product("bad-1",category=""))
        status,raw,_=self.request("/api/products")
        self.assertEqual(status,200)
        self.assertEqual(len(json.loads(raw)["products"]),2)

    def test_migrates_existing_hobby_volume_without_deleting_products(self):
        path=Path(self.tmp.name)/"legacy.db"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE products(sku TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,"
                       "price_cents INTEGER NOT NULL,stock INTEGER NOT NULL,active INTEGER NOT NULL,changed_at INTEGER NOT NULL)")
            db.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?)",
                       ("old-1","Older product","Existing SQLite data",1250,8,1,123))
        upgraded=CommerceStore(path)
        old=upgraded.products()[0]
        self.assertEqual(old["sku"],"old-1")
        self.assertEqual(old["category"],"Genel")
        self.assertEqual(old["price_cents"],1250)
        self.assertEqual(old["stock"],8)
        upgraded_again=CommerceStore(path)
        self.assertEqual(len(upgraded_again.products()),1)

    def test_photo_is_resized_and_exif_removed(self):
        normalized=normalize_product_photo(image_source("JPEG"),"image/jpeg")
        self.assertLessEqual(len(normalized),MAX_IMAGE)
        self.assertTrue(normalized.startswith(b"\xff\xd8\xff"))
        with Image.open(BytesIO(normalized)) as img:
            self.assertEqual(img.format,"JPEG")
            self.assertLessEqual(max(img.size),960)
            self.assertFalse(img.getexif(),"no EXIF, including GPS or private notes")
        raw_png=image_source("PNG")
        normalized_png=normalize_product_photo(raw_png,"image/png")
        with Image.open(BytesIO(normalized_png)) as img:
            self.assertEqual(img.format,"JPEG")

    def test_codec_rejects_invalid_bytes_and_types(self):
        for body,kind in [
            (b"hello","image/jpeg"),
            (image_source("PNG"),"image/jpeg"),
            (image_source("PNG"),"image/svg+xml"),
            (b"\0"*2_000_001,"image/png"),
        ]:
            with self.subTest(kind=kind,length=len(body)):
                with self.assertRaises(CommerceError):
                    normalize_product_photo(body,kind)

    def test_auth_upload_serve_replace_and_delete_image(self):
        self.store.set_product(product())
        body=image_source("PNG")
        route="/api/admin/products/coffee-1/image"
        self.assertEqual(self.request(route,"POST",body,"image/png")[0],401)
        cookie=self.login()
        self.assertEqual(self.request(route,"POST",body,"image/png",cookie,origin="https://evil.example")[0],403)
        self.assertEqual(self.request(route,"POST",b"not-an-image","image/png",cookie)[0],400)
        status,result,_=self.request(route,"POST",body,"image/png",cookie)
        self.assertEqual(status,200,result)
        self.assertTrue(json.loads(result)["has_image"])
        listing=self.store.products()[0]
        self.assertTrue(listing["has_image"])
        version=listing["image_version"]
        self.assertEqual(len(version),12)
        status,photo,headers=self.request("/api/images/coffee-1")
        self.assertEqual(status,200)
        self.assertEqual(headers["Content-Type"],"image/jpeg")
        self.assertIn("no-store",headers["Cache-Control"])
        with Image.open(BytesIO(photo)) as img:
            self.assertLessEqual(max(img.size),960)
        alternate=Image.new("RGB",(150,125),(220,40,15))
        out=BytesIO();alternate.save(out,format="PNG")
        status,result,_=self.request(route,"POST",out.getvalue(),"image/png",cookie)
        self.assertEqual(status,200,result)
        self.assertNotEqual(self.store.products()[0]["image_version"],version)
        self.assertEqual(self.request(route,"DELETE",cookie=cookie,origin="https://evil.example")[0],403)
        self.assertEqual(self.request(route,"DELETE",cookie=cookie)[0],200)
        self.assertEqual(self.request("/api/images/coffee-1")[0],404)
        self.assertFalse(self.store.products()[0]["has_image"])

    def test_unknown_sku_or_malformed_image_paths(self):
        cookie=self.login()
        raw=image_source("PNG")
        self.assertEqual(self.request("/api/admin/products/missing/image","POST",raw,"image/png",cookie)[0],404)
        self.assertEqual(self.request("/api/images/invalid-%20")[0],400)
        self.assertEqual(self.request("/api/admin/products/missing/image","DELETE",cookie=cookie)[0],404)

    def test_image_metadata_changes_not_cart_pricing(self):
        self.store.set_product(product())
        total=self.store.quote([{"sku":"coffee-1","quantity":2}])
        self.store.set_product_image("coffee-1",normalize_product_photo(image_source("PNG"),"image/png"))
        after=self.store.quote([{"sku":"coffee-1","quantity":2}])
        self.assertEqual(after["total_cents"],total["total_cents"])
        self.assertEqual(after["total_cents"],3000)
        self.assertEqual(self.store.products()[0]["category"],"Gıda")

    def test_frontend_is_mobile_and_real_upload(self):
        page=(ROOT/"storefront.html").read_text(encoding="utf-8")
        for needle in ('id="catalog-search"','id="catalog-category"','id="catalog-sort"',
                       'name="photo"','accept="image/jpeg,image/png,image/webp"',
                       'function photoUpload(', 'function removeProductPhoto(',
                       '"catalog-search").addEventListener("input",drawCatalog)'):
            self.assertIn(needle,page)
        self.assertNotIn('style="',page)
        status,raw,headers=self.request("/")
        self.assertEqual(status,200)
        self.assertIn("img-src 'self' data:",headers["Content-Security-Policy"])
        self.assertIn('id="catalog-search"',raw.decode())


if __name__=="__main__":
    unittest.main()
