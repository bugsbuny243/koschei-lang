"""Koschei Commerce: persistent product, order and stock state.

The SQLite database owns product and order durability. Koschei Lang owns cart
arithmetic; the Python layer handles HTTP, validation, SQL transactions and
authentication. There is no pricing fallback if Koschei is unavailable.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Callable, Iterator

ROOT = Path(__file__).resolve().parent
PRICING_SOURCE = ROOT / "pricing.ks"
SKU_RE = re.compile(r"[a-z][a-z0-9-]{2,31}\Z", re.ASCII)
ID_RE = re.compile(r"[0-9a-f]{24}\Z", re.ASCII)
KEY_RE = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,180}\Z", re.ASCII)
MAX_CENTS = 100_000_000
MAX_QUANTITY = 20
MAX_STOCK = 100_000
MAX_LINES = 25


class CommerceError(Exception):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def whole(value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise CommerceError("invalid_integer")
    return value


def clean_text(value: object, limit: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise CommerceError("invalid_text")
    v = value.strip()
    if (required and not v) or len(v) > limit or any(ord(x) < 32 for x in v):
        raise CommerceError("invalid_text")
    return v


def validate_product(data: object, existing_sku: str | None = None) -> dict:
    if not isinstance(data, dict):
        raise CommerceError("invalid_product")
    sku = clean_text(data.get("sku", existing_sku), 32)
    if not SKU_RE.fullmatch(sku) or (existing_sku is not None and sku != existing_sku):
        raise CommerceError("invalid_sku")
    name = clean_text(data.get("name"), 100)
    description = clean_text(data.get("description", ""), 1000, required=False)
    category = clean_text(data.get("category", "Genel"), 48)
    price = whole(data.get("price_cents"), 1, MAX_CENTS)
    stock = whole(data.get("stock"), 0, MAX_STOCK)
    active = data.get("active", True)
    if type(active) is not bool:
        raise CommerceError("invalid_active")
    return {"sku": sku, "name": name, "description": description,
            "category":category, "price_cents": price, "stock": stock, "active": int(active)}


def validate_lines(payload: object) -> list[tuple[str, int]]:
    if not isinstance(payload, list) or not 1 <= len(payload) <= MAX_LINES:
        raise CommerceError("invalid_cart")
    result = []
    seen: set[str] = set()
    for line in payload:
        if not isinstance(line, dict):
            raise CommerceError("invalid_line")
        sku = line.get("sku")
        if not isinstance(sku, str) or not SKU_RE.fullmatch(sku) or sku in seen:
            raise CommerceError("invalid_or_duplicate_sku")
        quantity = whole(line.get("quantity"), 1, MAX_QUANTITY)
        seen.add(sku)
        result.append((sku, quantity))
    return result


def validate_contact(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise CommerceError("invalid_contact")
    name = clean_text(payload.get("name"), 100)
    email = clean_text(payload.get("email"), 254)
    if not EMAIL_RE.fullmatch(email):
        raise CommerceError("invalid_email")
    note = clean_text(payload.get("note", ""), 300, required=False)
    return {"name": name, "email": email, "note": note}


def price_with_koschei(lines: list[dict]) -> tuple[int, int]:
    """Fail-closed pricing. No Python replacement of the Koschei computation."""
    if not 1 <= len(lines) <= MAX_LINES or not PRICING_SOURCE.is_file():
        raise CommerceError("pricing_unavailable", 503)
    protocol = "CART|1\n" + "".join(
        f"ROW|{row['quantity']}|{row['price_cents']}\n" for row in lines
    )
    if len(protocol) > 4096:
        raise CommerceError("pricing_unavailable", 503)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "koschei", "run",
             str(PRICING_SOURCE), "--max-steps", "120000"],
            input=protocol, text=True, encoding="utf-8",
            capture_output=True, timeout=7, check=False,
            cwd=ROOT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CommerceError("pricing_unavailable", 503) from exc
    if result.returncode or len(result.stdout) > 256:
        raise CommerceError("pricing_unavailable", 503)
    match = re.fullmatch(r"OK\|CART\|([0-9]{1,13})\|([0-9]{1,2})\|([0-9]{1,4})\n?", result.stdout)
    if not match:
        raise CommerceError("pricing_unavailable", 503)
    subtotal, count, total_quantity = map(int, match.groups())
    # Cross-check invariants; this is not a fallback arithmetic implementation.
    if count != len(lines) or total_quantity != sum(x["quantity"] for x in lines):
        raise CommerceError("pricing_invariant_failed", 503)
    if subtotal != sum(x["price_cents"] * x["quantity"] for x in lines):
        raise CommerceError("pricing_invariant_failed", 503)
    return subtotal, total_quantity


class CommerceStore:
    def __init__(self, path: str | Path, price_fn: Callable = price_with_koschei):
        self.path = str(path)
        self.price_fn = price_fn
        self.init_db()

    @contextmanager
    def connection(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.execute("COMMIT")
        except Exception:
            if write and db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def init_db(self) -> None:
        # sqlite3.executescript commits any open transaction; initialize
        # outside our write transaction and enable WAL for reliable readers.
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS products (
                    sku TEXT PRIMARY KEY,
                    name TEXT NOT NULL, description TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Genel',
                    price_cents INTEGER NOT NULL CHECK(price_cents BETWEEN 1 AND 100000000),
                    stock INTEGER NOT NULL CHECK(stock BETWEEN 0 AND 100000),
                    active INTEGER NOT NULL CHECK(active IN (0,1)),
                    changed_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('pending','accepted','fulfilled','cancelled')),
                    customer_name TEXT NOT NULL, customer_email TEXT NOT NULL,
                    customer_note TEXT NOT NULL,
                    subtotal_cents INTEGER NOT NULL,
                    total_cents INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS order_items (
                    order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    sku TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    unit_cents INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    line_cents INTEGER NOT NULL,
                    PRIMARY KEY(order_id,sku)
                );
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token_hash TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS product_images (
                    sku TEXT PRIMARY KEY REFERENCES products(sku) ON DELETE CASCADE,
                    data BLOB NOT NULL,
                    digest TEXT NOT NULL,
                    changed_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS orders_created ON orders(created_at DESC);
                CREATE INDEX IF NOT EXISTS sessions_expiry ON admin_sessions(expires_at);
                CREATE TABLE IF NOT EXISTS stock_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    delta INTEGER NOT NULL,
                    stock_after INTEGER NOT NULL CHECK(stock_after BETWEEN 0 AND 100000),
                    reason TEXT NOT NULL CHECK(reason IN
                        ('created','import','manual_edit','order_accept','order_cancel')),
                    order_id TEXT,
                    happened_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS stock_movements_recent
                    ON stock_movements(happened_at DESC,id DESC);
                CREATE INDEX IF NOT EXISTS stock_movements_by_sku
                    ON stock_movements(sku,id DESC);
            """)
            # Existing Hobby volumes must migrate without deleting older products.
            columns = {x["name"] for x in db.execute("PRAGMA table_info(products)")}
            if "category" not in columns:
                db.execute("ALTER TABLE products ADD COLUMN category TEXT NOT NULL DEFAULT 'Genel'")
            db.execute("CREATE INDEX IF NOT EXISTS products_category ON products(category)")

    @staticmethod
    def _product_row(row: sqlite3.Row) -> dict:
        return {"sku": row["sku"], "name": row["name"],
                "description": row["description"], "category": row["category"],
                "price_cents": row["price_cents"], "stock": row["stock"],
                "active": bool(row["active"]),
                "has_image": row["image_digest"] is not None,
                "image_version": (row["image_digest"][:12] if row["image_digest"] else None)}

    def products(self, public: bool = True) -> list[dict]:
        with self.connection() as db:
            sql = ("SELECT p.*, i.digest AS image_digest FROM products p "
                   "LEFT JOIN product_images i ON i.sku=p.sku " +
                   ("WHERE p.active=1 " if public else "") +
                   "ORDER BY p.name COLLATE NOCASE,p.sku LIMIT 1000")
            return [self._product_row(row) for row in db.execute(sql)]

    @staticmethod
    def _stock_event(db: sqlite3.Connection, sku: str, delta: int,
                     stock_after: int, reason: str,
                     order_id: str | None = None) -> None:
        db.execute(
            "INSERT INTO stock_movements (sku,delta,stock_after,reason,order_id,happened_at) "
            "VALUES(?,?,?,?,?,?)",
            (sku,delta,stock_after,reason,order_id,int(time.time()))
        )

    def stock_history(self, sku: str | None = None) -> list[dict]:
        if sku is not None and (not isinstance(sku,str) or not SKU_RE.fullmatch(sku)):
            raise CommerceError("invalid_sku")
        with self.connection() as db:
            if sku is None:
                events=db.execute(
                    "SELECT * FROM stock_movements ORDER BY id DESC LIMIT 200"
                ).fetchall()
            else:
                events=db.execute(
                    "SELECT * FROM stock_movements WHERE sku=? ORDER BY id DESC LIMIT 200",
                    (sku,)
                ).fetchall()
        return [
            {"id":x["id"],"sku":x["sku"],"delta":x["delta"],
             "stock_after":x["stock_after"],"reason":x["reason"],
             "order_id":x["order_id"],"happened_at":x["happened_at"]}
            for x in events
        ]

    def bulk_create_products(self, products: list[dict], dry_run: bool = True) -> dict:
        # Parse/validate before this method; never modify existing products via CSV.
        if not isinstance(products,list) or not 1 <= len(products) <= 100:
            raise CommerceError("invalid_import_count")
        rows=[validate_product(p) for p in products]
        skus=[p["sku"] for p in rows]
        if len(set(skus)) != len(skus):
            raise CommerceError("import_duplicate_sku",409)
        with self.connection(write=not dry_run) as db:
            existing_count=db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            if existing_count + len(rows)>1000:
                raise CommerceError("catalog_limit",409)
            placeholders=",".join("?" for _ in rows)
            existing=db.execute(
                "SELECT sku FROM products WHERE sku IN ("+placeholders+")",skus
            ).fetchall()
            if existing:
                raise CommerceError("import_sku_exists",409)
            if not dry_run:
                now=int(time.time())
                for row in rows:
                    db.execute(
                        "INSERT INTO products"
                        "(sku,name,description,category,price_cents,stock,active,changed_at)"
                        " VALUES(?,?,?,?,?,?,?,?)",
                        (row["sku"],row["name"],row["description"],row["category"],
                         row["price_cents"],row["stock"],row["active"],now)
                    )
                    self._stock_event(db,row["sku"],row["stock"],row["stock"],"import")
        return {"count":len(rows),"dry_run":dry_run,"created":0 if dry_run else len(rows),
                "sample":[{"sku":r["sku"],"name":r["name"],"stock":r["stock"]} for r in rows[:10]]}

    @contextmanager
    def backup_copy(self) -> Iterator[Path]:
        """Consistent SQLite snapshot with administrative sessions removed.

        Backup is created in ephemeral /tmp, not on the 512MB live volume.
        Users must keep downloaded snapshots securely: they contain customer PII.
        """
        with tempfile.TemporaryDirectory(prefix="koschei-commerce-backup-") as folder:
            destination=Path(folder)/"commerce.sqlite3"
            with self.connection() as source:
                with closing(sqlite3.connect(destination)) as target:
                    source.backup(target,pages=128,sleep=0.05)
                    # Ensure a self-contained backup file (no .sqlite3-wal needed).
                    target.execute("PRAGMA journal_mode=DELETE")
                    target.execute("DELETE FROM admin_sessions")
                    target.commit()
                    check=target.execute("PRAGMA quick_check").fetchone()[0]
                    if check!="ok":
                        raise CommerceError("backup_integrity_failed",503)
            if destination.stat().st_size>64*1024*1024:
                raise CommerceError("backup_too_large",413)
            yield destination

    def set_product(self, data: object, sku: str | None = None) -> dict:
        row = validate_product(data, existing_sku=sku)
        now = int(time.time())
        with self.connection(write=True) as db:
            if sku is None:
                try:
                    db.execute(
                        "INSERT INTO products "
                        "(sku,name,description,category,price_cents,stock,active,changed_at) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (row["sku"],row["name"],row["description"],row["category"],
                         row["price_cents"],row["stock"],row["active"],now)
                    )
                except sqlite3.IntegrityError as exc:
                    raise CommerceError("sku_exists", 409) from exc
                self._stock_event(db,row["sku"],row["stock"],row["stock"],"created")
            else:
                previous=db.execute(
                    "SELECT stock FROM products WHERE sku=?",(sku,)
                ).fetchone()
                if previous is None:
                    raise CommerceError("product_not_found",404)
                result = db.execute(
                    "UPDATE products SET name=?,description=?,category=?,price_cents=?,stock=?,active=?,changed_at=? WHERE sku=?",
                    (row["name"],row["description"],row["category"],
                     row["price_cents"],row["stock"],row["active"],now,sku)
                )
                if result.rowcount != 1:
                    raise CommerceError("product_not_found",404)
                delta=row["stock"]-previous["stock"]
                if delta:
                    self._stock_event(db,row["sku"],delta,row["stock"],"manual_edit")
        with self.connection() as db:
            saved = db.execute(
                "SELECT p.*, i.digest AS image_digest FROM products p "
                "LEFT JOIN product_images i ON i.sku=p.sku WHERE p.sku=?",
                (row["sku"],)
            ).fetchone()
        return self._product_row(saved)

    def product_image(self, sku: str) -> tuple[bytes,str]:
        if not isinstance(sku,str) or not SKU_RE.fullmatch(sku):
            raise CommerceError("invalid_sku")
        with self.connection() as db:
            row = db.execute("SELECT data,digest FROM product_images WHERE sku=?",(sku,)).fetchone()
        if row is None:
            raise CommerceError("image_not_found",404)
        return row["data"],row["digest"]

    def set_product_image(self, sku: str, data: bytes) -> str:
        if not isinstance(sku,str) or not SKU_RE.fullmatch(sku):
            raise CommerceError("invalid_sku")
        if not isinstance(data,bytes) or not 1 <= len(data) <= 500000:
            raise CommerceError("invalid_product_image")
        digest = hashlib.sha256(data).hexdigest()
        with self.connection(write=True) as db:
            if db.execute("SELECT 1 FROM products WHERE sku=?",(sku,)).fetchone() is None:
                raise CommerceError("product_not_found",404)
            db.execute(
                "INSERT INTO product_images(sku,data,digest,changed_at) VALUES(?,?,?,?) "
                "ON CONFLICT(sku) DO UPDATE SET data=excluded.data,"
                "digest=excluded.digest,changed_at=excluded.changed_at",
                (sku,data,digest,int(time.time()))
            )
        return digest

    def delete_product_image(self, sku: str) -> None:
        if not isinstance(sku,str) or not SKU_RE.fullmatch(sku):
            raise CommerceError("invalid_sku")
        with self.connection(write=True) as db:
            if db.execute("SELECT 1 FROM products WHERE sku=?",(sku,)).fetchone() is None:
                raise CommerceError("product_not_found",404)
            db.execute("DELETE FROM product_images WHERE sku=?",(sku,))


    def _checked_cart(self, db: sqlite3.Connection, lines: list[tuple[str, int]]) -> list[dict]:
        cart = []
        for sku,qty in lines:
            row = db.execute("SELECT * FROM products WHERE sku=? AND active=1",(sku,)).fetchone()
            if row is None:
                raise CommerceError("product_unavailable",409)
            if row["stock"] < qty:
                raise CommerceError("insufficient_stock",409)
            cart.append({"sku":sku,"name":row["name"],"price_cents":row["price_cents"],
                         "quantity":qty})
        return cart

    def quote(self, payload: object) -> dict:
        lines = validate_lines(payload)
        with self.connection() as db:
            cart = self._checked_cart(db, lines)
        subtotal,quantity = self.price_fn(cart)
        return {"currency":"TRY","subtotal_cents":subtotal,"total_cents":subtotal,
                "quantity":quantity,"items":[{**x,"line_cents":x["price_cents"]*x["quantity"]} for x in cart],
                "fulfillment":"pickup","payment_status":"not_collected"}

    def create_order(self, payload: object) -> dict:
        if not isinstance(payload,dict):
            raise CommerceError("invalid_order")
        key = payload.get("idempotency_key")
        if not isinstance(key,str) or not KEY_RE.fullmatch(key):
            raise CommerceError("invalid_idempotency_key")
        contact = validate_contact(payload.get("customer"))
        lines = validate_lines(payload.get("items"))
        clean_request = {"customer":contact,"items":lines}
        digest = hashlib.sha256(json.dumps(clean_request,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with self.connection(write=True) as db:
            existing = db.execute("SELECT * FROM orders WHERE idempotency_key=?",(key,)).fetchone()
            if existing:
                if not hmac.compare_digest(existing["request_hash"],digest):
                    raise CommerceError("idempotency_conflict",409)
                return self._order_result(db,existing)
            cart = self._checked_cart(db,lines)
            subtotal,_ = self.price_fn(cart)
            now=int(time.time())
            oid=secrets.token_hex(12)
            db.execute(
                """INSERT INTO orders
                   (id,status,customer_name,customer_email,customer_note,subtotal_cents,total_cents,
                   idempotency_key,request_hash,created_at,updated_at)
                   VALUES (?,'pending',?,?,?,?,?,?,?,?,?)""",
                (oid,contact["name"],contact["email"],contact["note"],subtotal,subtotal,key,digest,now,now)
            )
            db.executemany(
                "INSERT INTO order_items VALUES(?,?,?,?,?,?)",
                [(oid,x["sku"],x["name"],x["price_cents"],x["quantity"],
                  x["price_cents"]*x["quantity"]) for x in cart]
            )
            return self._order_result(db,db.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone())

    def _order_result(self, db: sqlite3.Connection, row: sqlite3.Row, admin: bool = False) -> dict:
        result = {"id":row["id"],"status":row["status"],"currency":"TRY",
                  "subtotal_cents":row["subtotal_cents"],"total_cents":row["total_cents"],
                  "created_at":row["created_at"],"fulfillment":"pickup",
                  "payment_status":"not_collected",
                  "items":[{"sku":x["sku"],"name":x["product_name"],
                            "price_cents":x["unit_cents"],"quantity":x["quantity"],
                            "line_cents":x["line_cents"]} for x in db.execute(
                                "SELECT * FROM order_items WHERE order_id=? ORDER BY sku",(row["id"],)
                            )]}
        if admin:
            result["customer"]={"name":row["customer_name"],"email":row["customer_email"],
                                "note":row["customer_note"]}
        return result

    def orders(self) -> list[dict]:
        with self.connection() as db:
            return [self._order_result(db,row,admin=True) for row in db.execute(
                "SELECT * FROM orders ORDER BY created_at DESC,id DESC LIMIT 100"
            )]

    def change_order(self, oid: str, action: str) -> dict:
        if not isinstance(oid,str) or not ID_RE.fullmatch(oid):
            raise CommerceError("invalid_order_id")
        if action not in ("accept","fulfill","cancel","redact"):
            raise CommerceError("invalid_action")
        with self.connection(write=True) as db:
            order = db.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
            if not order:
                raise CommerceError("order_not_found",404)
            previous=order["status"]
            if action=="accept" and previous=="pending":
                items=db.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY sku",(oid,)).fetchall()
                for item in items:
                    r=db.execute(
                        "UPDATE products SET stock=stock-?,changed_at=? WHERE sku=? AND stock>=?",
                        (item["quantity"],int(time.time()),item["sku"],item["quantity"]))
                    if r.rowcount!=1:
                        raise CommerceError("insufficient_stock",409)
                    after=db.execute(
                        "SELECT stock FROM products WHERE sku=?",(item["sku"],)
                    ).fetchone()["stock"]
                    self._stock_event(
                        db,item["sku"],-item["quantity"],after,"order_accept",oid
                    )
                target="accepted"
            elif action=="fulfill" and previous=="accepted":
                target="fulfilled"
            elif action=="cancel" and previous in ("pending","accepted"):
                if previous=="accepted":
                    items=db.execute("SELECT * FROM order_items WHERE order_id=?",(oid,)).fetchall()
                    for item in items:
                        r=db.execute(
                            "UPDATE products SET stock=stock+?,changed_at=? WHERE sku=? AND stock+?<=?",
                            (item["quantity"],int(time.time()),item["sku"],item["quantity"],MAX_STOCK))
                        if r.rowcount!=1:
                            raise CommerceError("stock_restoration_failed",409)
                        after=db.execute(
                            "SELECT stock FROM products WHERE sku=?",(item["sku"],)
                        ).fetchone()["stock"]
                        self._stock_event(
                            db,item["sku"],item["quantity"],after,"order_cancel",oid
                        )
                target="cancelled"
            elif action=="redact" and previous in ("cancelled","fulfilled"):
                db.execute(
                    "UPDATE orders SET customer_name=?,customer_email=?,customer_note='',updated_at=? WHERE id=?",
                    ("[redacted]","redacted@invalid.example",int(time.time()),oid)
                )
                target=previous
            else:
                raise CommerceError("invalid_order_transition",409)
            db.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?",
                       (target,int(time.time()),oid))
            return self._order_result(db,db.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone(),admin=True)

    def login_session(self) -> str:
        token=secrets.token_hex(32)
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.connection(write=True) as db:
            db.execute("DELETE FROM admin_sessions WHERE expires_at<?",(int(time.time()),))
            db.execute("INSERT INTO admin_sessions VALUES(?,?)",(digest,int(time.time())+28800))
        return token

    def is_admin(self, token: str) -> bool:
        if not isinstance(token,str) or not re.fullmatch(r"[0-9a-f]{64}",token):
            return False
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.connection() as db:
            return db.execute("SELECT 1 FROM admin_sessions WHERE token_hash=? AND expires_at>?",
                              (digest,int(time.time()))).fetchone() is not None

    def logout_session(self, token: str) -> None:
        if isinstance(token,str) and re.fullmatch(r"[0-9a-f]{64}",token):
            digest=hashlib.sha256(token.encode()).hexdigest()
            with self.connection(write=True) as db:
                db.execute("DELETE FROM admin_sessions WHERE token_hash=?",(digest,))
