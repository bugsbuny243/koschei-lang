"""Koschei Commerce integration tests: real pricing, stock, auth, SQLite and HTTP.

This is a merchandise ordering service, not a simulated calculator.
Each test uses a real isolated SQLite database; prices run in Koschei Lang.
"""
from __future__ import annotations

import unittest

try:
    import PIL  # noqa: F401  (Koschei Commerce needs Pillow for photos)
except ImportError:  # the core CI does not install it; commerce-core.yml does
    raise unittest.SkipTest("Pillow is not installed")

import importlib.util
import json
from pathlib import Path
import secrets
import sys
import tempfile
from threading import Thread
from http.server import ThreadingHTTPServer
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT = Path(__file__).resolve().parents[1] / "products" / "commerce"
sys.path.insert(0, str(PROJECT))
from storage import CommerceError, CommerceStore, price_with_koschei
from server import Config, make_handler

ORIGIN = "https://shop.example.test"
SECRET = "a-strong-merchants-passphrase-123456"


def product(sku="coffee-1",stock=3,price=1500):
    return {"sku":sku,"name":"Premium Coffee",
            "description":"Fresh roasted coffee beans",
            "stock":stock,"price_cents":price,"active":True}


class CommerceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=CommerceStore(Path(self.tmp.name) / "commerce.db")
        handler=make_handler(self.db,Config(ORIGIN,SECRET,"Koschei Store",True))
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler)
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        thread=Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(),self.server.server_close(),thread.join(timeout=3)))

    def http(self,path,method="GET",body=None,cookie=None,origin=ORIGIN):
        headers={}
        if body is not None:
            headers["Content-Type"]="application/json"
        if origin is not None:
            headers["Origin"]=origin
        if cookie:
            headers["Cookie"]=cookie
        request=Request(self.base+path,method=method,headers=headers,
                        data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request,timeout=15) as response:
                data=response.read()
                return response.status,json.loads(data) if data and path!="/" else data,response.headers
        except HTTPError as error:
            payload=json.loads(error.read().decode())
            return error.code,payload,error.headers

    def admin_cookie(self):
        status,data,headers=self.http("/api/admin/login","POST",{"password":SECRET})
        self.assertEqual(status,200,data)
        cookie=headers["Set-Cookie"]
        self.assertIn("Secure",cookie)
        self.assertIn("HttpOnly",cookie)
        self.assertIn("SameSite=Strict",cookie)
        return cookie.split(";",1)[0]

    def seed(self,cookie=None,sku="coffee-1",stock=3,price=1500):
        cookie=cookie or self.admin_cookie()
        status,result,_=self.http("/api/admin/products","POST",product(sku,stock,price),cookie)
        self.assertEqual(status,201,result)
        return cookie

    def order_payload(self,sku="coffee-1",qty=2,key=None):
        return {"idempotency_key":key or secrets.token_hex(16),
                "customer":{"name":"Test Guest","email":"guest@example.test",
                            "note":"Store pickup"},
                "items":[{"sku":sku,"quantity":qty}]}

    def test_language_pricing_direct(self):
        result=price_with_koschei([
            {"price_cents":1299,"quantity":2},
            {"price_cents":101,"quantity":3}])
        self.assertEqual(result,(2901,5))
        with self.assertRaisesRegex(CommerceError,"pricing_unavailable"):
            price_with_koschei([])

    def test_public_catalog_and_checkout_are_real(self):
        cookie=self.seed()
        status,config,_=self.http("/api/config")
        self.assertEqual(status,200)
        self.assertFalse(config["payments_enabled"])
        self.assertTrue(config["orders_enabled"])
        status,catalog,_=self.http("/api/products")
        self.assertEqual(status,200)
        self.assertEqual(len(catalog["products"]),1)
        status,quote,_=self.http("/api/cart/quote","POST",
                                {"items":[{"sku":"coffee-1","quantity":2}]})
        self.assertEqual(status,200,quote)
        self.assertEqual(quote["total_cents"],3000)
        self.assertEqual(quote["quantity"],2)
        status,order,_=self.http("/api/orders","POST",self.order_payload())
        self.assertEqual(status,201,order)
        ref=order["order"]["id"]
        self.assertEqual(len(ref),24)
        self.assertEqual(order["order"]["status"],"pending")
        self.assertEqual(order["order"]["total_cents"],3000)
        self.assertNotIn("customer",order["order"],"guest API must not echo customer data")
        self.assertEqual(self.db.products()[0]["stock"],3,"unapproved requests must not reserve stock")
        status,admin_orders,_=self.http("/api/admin/orders",cookie=cookie)
        self.assertEqual(status,200,admin_orders)
        self.assertEqual(admin_orders["orders"][0]["customer"]["email"],"guest@example.test")
        self.assertEqual(len(admin_orders["orders"][0]["items"]),1)
        status,accepted,_=self.http("/api/admin/orders/"+ref,"PATCH",{"action":"accept"},cookie)
        self.assertEqual(status,200,accepted)
        self.assertEqual(accepted["order"]["status"],"accepted")
        self.assertEqual(self.db.products()[0]["stock"],1)
        status,fulfilled,_=self.http("/api/admin/orders/"+ref,"PATCH",{"action":"fulfill"},cookie)
        self.assertEqual(status,200,fulfilled)
        self.assertEqual(fulfilled["order"]["status"],"fulfilled")
        status,invalid,_=self.http("/api/admin/orders/"+ref,"PATCH",{"action":"cancel"},cookie)
        self.assertEqual(status,409,invalid)
        status,redacted,_=self.http("/api/admin/orders/"+ref,"PATCH",{"action":"redact"},cookie)
        self.assertEqual(status,200,redacted)
        self.assertEqual(redacted["order"]["status"],"fulfilled")
        self.assertEqual(redacted["order"]["customer"]["email"],"redacted@invalid.example")
        self.assertEqual(redacted["order"]["customer"]["note"],"")
        self.assertEqual(self.db.products()[0]["stock"],1)

    def test_cancel_restores_stock_and_repeated_transitions_rejected(self):
        cookie=self.seed(stock=2)
        req=self.order_payload(qty=2)
        result=self.http("/api/orders","POST",req)[1]["order"]
        ref=result["id"]
        self.assertEqual(self.http("/api/admin/orders/"+ref,"PATCH",{"action":"accept"},cookie)[0],200)
        self.assertEqual(self.db.products()[0]["stock"],0)
        self.assertEqual(self.http("/api/admin/orders/"+ref,"PATCH",{"action":"cancel"},cookie)[0],200)
        self.assertEqual(self.db.products()[0]["stock"],2)
        self.assertEqual(self.http("/api/admin/orders/"+ref,"PATCH",{"action":"cancel"},cookie)[0],409)
        status,redacted,_=self.http("/api/admin/orders/"+ref,"PATCH",{"action":"redact"},cookie)
        self.assertEqual(status,200)
        self.assertEqual(redacted["order"]["customer"]["name"],"[redacted]")

    def test_two_pending_orders_cannot_oversell(self):
        cookie=self.seed(stock=1)
        a=self.http("/api/orders","POST",self.order_payload(qty=1))[1]["order"]["id"]
        b=self.http("/api/orders","POST",self.order_payload(qty=1))[1]["order"]["id"]
        self.assertEqual(self.http("/api/admin/orders/"+a,"PATCH",{"action":"accept"},cookie)[0],200)
        self.assertEqual(self.http("/api/admin/orders/"+b,"PATCH",{"action":"accept"},cookie)[0],409)
        self.assertEqual(self.db.products()[0]["stock"],0)
        orders=self.db.orders()
        self.assertEqual({x["id"]:x["status"] for x in orders}[b],"pending")

    def test_retries_are_idempotent_and_conflicts_blocked(self):
        self.seed(stock=5)
        req=self.order_payload(qty=2)
        a=self.http("/api/orders","POST",req)
        b=self.http("/api/orders","POST",req)
        self.assertEqual(a[0],201)
        self.assertEqual(b[0],201)
        self.assertEqual(a[1]["order"]["id"],b[1]["order"]["id"])
        self.assertEqual(len(self.db.orders()),1)
        changed={**req,"customer":{**req["customer"],"name":"Different"}}
        conflict=self.http("/api/orders","POST",changed)
        self.assertEqual(conflict[0],409)
        self.assertEqual(conflict[1]["error"],"idempotency_conflict")

    def test_product_admin_auth_required_and_status(self):
        self.assertEqual(self.http("/api/admin/products")[0],401)
        self.assertEqual(self.http("/api/admin/products","POST",product())[0],401)
        self.assertEqual(self.http("/api/admin/login","POST",{"password":"wrong"})[0],401)
        self.assertEqual(self.http("/api/admin/login","POST",{"password":SECRET},origin=None)[0],403)
        cookie=self.seed()
        updated=product(stock=7,price=1999)
        updated["active"]=False
        status,data,_=self.http("/api/admin/products/coffee-1","PATCH",updated,cookie)
        self.assertEqual(status,200,data)
        self.assertEqual(data["product"]["price_cents"],1999)
        self.assertFalse(data["product"]["active"])
        self.assertEqual(len(self.db.products(public=True)),0)
        self.assertEqual(len(self.db.products(public=False)),1)
        self.assertEqual(self.http("/api/admin/logout","POST",{},cookie)[0],200)
        self.assertEqual(self.http("/api/admin/orders",cookie=cookie)[0],401)

    def test_cross_origin_and_validation(self):
        cookie=self.seed()
        self.assertEqual(self.http("/api/cart/quote","POST",{"items":[]},origin="https://evil.example")[0],403)
        self.assertEqual(self.http("/api/admin/orders",cookie=None)[0],401)
        self.assertEqual(self.http("/api/cart/quote","POST",{"items":[{"sku":"coffee-1","quantity":True}]} )[0],400)
        self.assertEqual(self.http("/api/cart/quote","POST",{"items":[{"sku":"coffee-1","quantity":4}]} )[0],409)
        self.assertEqual(self.http("/api/orders","POST",{**self.order_payload(),"customer":{"name":"A","email":"invalid"}})[0],400)
        bad=product(sku="SQL;DROP TABLE",stock=4)
        self.assertEqual(self.http("/api/admin/products","POST",bad,cookie)[0],400)
        self.assertEqual(self.http("/api/admin/products","POST",product(),cookie)[0],409)
        self.assertEqual(self.http("/api/admin/orders/"+"b"*24,"PATCH",{"action":"accept"},cookie)[0],404)

    def test_html_security_and_order_flag(self):
        with urlopen(self.base+"/",timeout=10) as response:
            html=response.read().decode()
            csp=response.headers["Content-Security-Policy"]
            self.assertIn("script-src 'nonce-",csp)
            self.assertIn("style-src 'nonce-",csp)
            self.assertIn('id="order-form"',html)
            self.assertIn('id="merchant-orders"',html)
            self.assertIn("kredi kartı",html)
            self.assertNotIn("https://cdn.",html)
            self.assertNotIn('style="',html,"all styles must comply with the nonce CSP")
        restricted=make_handler(self.db,Config(ORIGIN,SECRET,accept_orders=False))
        alt=ThreadingHTTPServer(("127.0.0.1",0),restricted)
        thread=Thread(target=alt.serve_forever,daemon=True);thread.start()
        try:
            req=Request(f"http://127.0.0.1:{alt.server_port}/api/orders",method="POST",
                        headers={"Content-Type":"application/json","Origin":ORIGIN},
                        data=json.dumps(self.order_payload()).encode())
            with self.assertRaises(HTTPError) as error:
                urlopen(req,timeout=10)
            self.assertEqual(error.exception.code,503)
        finally:
            alt.shutdown();alt.server_close();thread.join(timeout=3)

    def test_schema_survives_reopen(self):
        self.db.set_product(product())
        again=CommerceStore(Path(self.tmp.name)/"commerce.db")
        self.assertEqual(again.products()[0]["name"],"Premium Coffee")
        self.assertTrue((Path(self.tmp.name)/"commerce.db").exists())


if __name__=="__main__":
    unittest.main()
