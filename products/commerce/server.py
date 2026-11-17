"""Standalone self-hosted Koschei Commerce HTTP server (standard-library only).

Use a persistent /data volume. Browser sessions cannot authorize arbitrary
execution; order pricing is delegated to the fixed Koschei pricing.ks source.
No payment credentials, payment links or card data are accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from email.utils import formatdate
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from storage import CommerceError, CommerceStore
from image_codec import MAX_UPLOAD, normalize_product_photo

HERE = Path(__file__).resolve().parent
STORE_HTML = HERE / "storefront.html"
BODY_LIMIT = 12288
SESSION_COOKIE = "__Host-koschei_merchant"


@dataclass(frozen=True)
class Config:
    public_origin: str
    admin_password: str
    store_name: str = "Koschei Commerce"
    accept_orders: bool = False

    def validate(self) -> None:
        parsed = urlsplit(self.public_origin)
        if not parsed.hostname or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("COMMERCE_PUBLIC_ORIGIN must be an exact origin")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1","localhost")):
            raise ValueError("Production origin must use HTTPS")
        if len(self.admin_password) < 16:
            raise ValueError("Admin password must be at least 16 characters")
        if not 1 <= len(self.store_name) <= 80:
            raise ValueError("Invalid store name")


class WindowLimit:
    def __init__(self, max_hits: int, seconds: int):
        self.max_hits,self.seconds=max_hits,seconds
        self.lock=threading.Lock()
        self.hits: dict[str,list[float]]={}

    def allow(self, key: str) -> bool:
        now=time.monotonic()
        with self.lock:
            if len(self.hits) > 5000:
                self.hits={k:v for k,v in self.hits.items() if v and v[-1]>now-self.seconds}
            recent=[t for t in self.hits.get(key,[]) if t>now-self.seconds]
            if len(recent)>=self.max_hits:
                self.hits[key]=recent
                return False
            recent.append(now)
            self.hits[key]=recent
            return True


def make_handler(store: CommerceStore, config: Config):
    config.validate()
    login_limit=WindowLimit(5,900)
    orders_limit=WindowLimit(15,3600)
    public_quote_limit=WindowLimit(120,3600)
    photo_limit=WindowLimit(30,3600)

    class Handler(BaseHTTPRequestHandler):
        server_version = "KoscheiCommerce/0.1"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(12)

        def log_message(self, format, *args):
            # Never log credentials, cookies, checkout PII or full request bodies.
            return

        def _send(self, status: int, content: bytes, content_type: str,
                  extra: dict[str,str] | None = None, nonce: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(content)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()")
            if nonce:
                self.send_header("Content-Security-Policy",
                    "default-src 'none'; script-src 'nonce-"+nonce+
                    "'; style-src 'nonce-"+nonce+
                    "'; connect-src 'self'; img-src 'self' data:; "
                    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            else:
                self.send_header("Content-Security-Policy","default-src 'none'; frame-ancestors 'none'")
            for key,value in (extra or {}).items():
                self.send_header(key,value)
            self.end_headers()
            self.wfile.write(content)

        def _json(self,status:int,body:dict|list,extra:dict[str,str]|None=None):
            encoded=json.dumps(body,ensure_ascii=False,separators=(",",":")).encode("utf-8")
            self._send(status,encoded,"application/json; charset=utf-8",extra)

        def _err(self,err:CommerceError):
            self._json(err.status,{"error":err.code})

        def _body(self) -> object:
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
                raise CommerceError("invalid_content_type",415)
            try:
                raw_length=int(self.headers.get("Content-Length","0"))
            except ValueError:
                raw_length=-1
            if not 1<=raw_length<=BODY_LIMIT:
                self.close_connection=True
                raise CommerceError("request_size_invalid",413)
            data=self.rfile.read(raw_length)
            try:
                return json.loads(data.decode("utf-8"))
            except (ValueError,UnicodeDecodeError) as exc:
                raise CommerceError("invalid_json") from exc

        def _image_body(self) -> bytes:
            if self.headers.get("Transfer-Encoding"):
                raise CommerceError("invalid_transfer_encoding",415)
            try:
                length=int(self.headers.get("Content-Length","0"))
            except ValueError:
                length=-1
            if not 1<=length<=MAX_UPLOAD:
                self.close_connection=True
                raise CommerceError("image_size_invalid",413)
            return self.rfile.read(length)

        def _origin(self):
            origin=self.headers.get("Origin")
            if origin!=config.public_origin:
                raise CommerceError("origin_denied",403)

        def _token(self) -> str:
            raw=self.headers.get("Cookie","")
            if len(raw)>4096:
                return ""
            try:
                jar=SimpleCookie()
                jar.load(raw)
                cookie=jar.get(SESSION_COOKIE)
                return cookie.value if cookie else ""
            except Exception:
                return ""

        def _admin(self):
            if not store.is_admin(self._token()):
                raise CommerceError("unauthorized",401)

        @staticmethod
        def _cookie(token:str,expired:bool=False)->str:
            return (SESSION_COOKIE+"="+token+
                    "; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age="+
                    ("0" if expired else "28800"))

        def _route(self):
            return urlsplit(self.path).path

        def do_GET(self):
            path=self._route()
            try:
                if path=="/health":
                    self._json(200,{"status":"ok"})
                elif path in ("/","/admin"):
                    nonce=secrets.token_urlsafe(18)
                    source=STORE_HTML.read_text(encoding="utf-8")
                    source=source.replace("__NONCE__",nonce).replace("__STORE_NAME__",html.escape(config.store_name,quote=True))
                    self._send(200,source.encode("utf-8"),"text/html; charset=utf-8",nonce=nonce)
                elif path=="/api/config":
                    self._json(200,{"name":config.store_name,"currency":"TRY",
                                    "pickup_only":True,"orders_enabled":config.accept_orders,
                                    "payments_enabled":False})
                elif path=="/api/products":
                    self._json(200,{"products":store.products(public=True),"currency":"TRY"})
                elif path.startswith("/api/images/"):
                    sku=path.removeprefix("/api/images/")
                    data,digest=store.product_image(sku)
                    self._send(200,data,"image/jpeg",{"ETag":'"'+digest+'"',"Content-Disposition":"inline"})
                elif path=="/api/admin/session":
                    self._json(200,{"authenticated":store.is_admin(self._token())})
                elif path=="/api/admin/products":
                    self._admin()
                    self._json(200,{"products":store.products(public=False)})
                elif path=="/api/admin/orders":
                    self._admin()
                    self._json(200,{"orders":store.orders()})
                else:
                    self._json(404,{"error":"not_found"})
            except CommerceError as err:
                self._err(err)
            except Exception:
                self._json(503,{"error":"service_unavailable"})

        def do_POST(self):
            path=self._route()
            try:
                self._origin()
                if path=="/api/admin/login":
                    if not login_limit.allow(self.client_address[0]):
                        raise CommerceError("login_rate_limited",429)
                    body=self._body()
                    password=body.get("password") if isinstance(body,dict) else None
                    if not isinstance(password,str) or not hmac.compare_digest(password,config.admin_password):
                        raise CommerceError("invalid_credentials",401)
                    token=store.login_session()
                    self._json(200,{"authenticated":True},{"Set-Cookie":self._cookie(token)})
                elif path=="/api/admin/logout":
                    self._admin()
                    store.logout_session(self._token())
                    self._json(200,{"authenticated":False},
                               {"Set-Cookie":self._cookie("",expired=True)})
                elif path=="/api/cart/quote":
                    if not public_quote_limit.allow(self.client_address[0]):
                        raise CommerceError("rate_limited",429)
                    body=self._body()
                    lines=body.get("items") if isinstance(body,dict) else None
                    self._json(200,store.quote(lines))
                elif path=="/api/orders":
                    if not config.accept_orders:
                        raise CommerceError("orders_disabled",503)
                    if not orders_limit.allow(self.client_address[0]):
                        raise CommerceError("rate_limited",429)
                    self._json(201,{"order":store.create_order(self._body())})
                elif path.startswith("/api/admin/products/") and path.endswith("/image"):
                    self._admin()
                    if not photo_limit.allow(self.client_address[0]):
                        raise CommerceError("image_rate_limited",429)
                    sku=path.removeprefix("/api/admin/products/").removesuffix("/image").strip("/")
                    image=normalize_product_photo(
                        self._image_body(),self.headers.get("Content-Type","").split(";")[0].strip().lower()
                    )
                    digest=store.set_product_image(sku,image)
                    self._json(200,{"sku":sku,"image_version":digest[:12],"has_image":True})
                elif path=="/api/admin/products":
                    self._admin()
                    self._json(201,{"product":store.set_product(self._body())})
                else:
                    self._json(404,{"error":"not_found"})
            except CommerceError as err:
                self._err(err)
            except Exception:
                self._json(503,{"error":"service_unavailable"})

        def do_PATCH(self):
            path=self._route()
            try:
                self._origin()
                self._admin()
                if path.startswith("/api/admin/products/"):
                    sku=path.rsplit("/",1)[-1]
                    self._json(200,{"product":store.set_product(self._body(),sku=sku)})
                elif path.startswith("/api/admin/orders/"):
                    oid=path.rsplit("/",1)[-1]
                    body=self._body()
                    action=body.get("action") if isinstance(body,dict) else None
                    self._json(200,{"order":store.change_order(oid,action)})
                else:
                    self._json(404,{"error":"not_found"})
            except CommerceError as err:
                self._err(err)
            except Exception:
                self._json(503,{"error":"service_unavailable"})

        def do_DELETE(self):
            path=self._route()
            try:
                self._origin()
                self._admin()
                if path.startswith("/api/admin/products/") and path.endswith("/image"):
                    sku=path.removeprefix("/api/admin/products/").removesuffix("/image").strip("/")
                    store.delete_product_image(sku)
                    self._json(200,{"sku":sku,"has_image":False})
                else:
                    self._json(404,{"error":"not_found"})
            except CommerceError as err:
                self._err(err)
            except Exception:
                self._json(503,{"error":"service_unavailable"})

    return Handler


def run_server():
    path=os.environ.get("COMMERCE_DB_PATH","")
    if not path.startswith("/data/"):
        raise RuntimeError("COMMERCE_DB_PATH must point to /data/ on a persistent volume")
    if not Path("/data").is_dir():
        raise RuntimeError("Persistent /data volume is required")
    cfg=Config(
        public_origin=os.environ["COMMERCE_PUBLIC_ORIGIN"],
        admin_password=os.environ["COMMERCE_ADMIN_PASSWORD"],
        store_name=os.environ.get("COMMERCE_STORE_NAME","Koschei Commerce"),
        accept_orders=os.environ.get("COMMERCE_ACCEPT_ORDERS","0")=="1",
    )
    cfg.validate()
    store=CommerceStore(path)
    addr="0.0.0.0",int(os.environ.get("PORT","8080"))
    httpd=ThreadingHTTPServer(addr,make_handler(store,cfg))
    httpd.daemon_threads=True
    print("Koschei Commerce ready on "+str(addr[1])+
          " / orders="+("enabled" if cfg.accept_orders else "disabled"),flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__=="__main__":
    run_server()
