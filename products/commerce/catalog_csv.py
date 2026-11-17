"""Bounded create-only product CSV importer for the merchant operations panel.

Format: UTF-8 (optional BOM), semicolon-separated, exact header
sku;name;category;description;price_try;stock;active
No updates, photos or other side effects. Dry-run is provided by CommerceStore.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
import re

from storage import CommerceError, validate_product

MAX_CSV_BYTES=65_536
COLUMNS=("sku","name","category","description","price_try","stock","active")
PRICE_RE=re.compile(r"(?:0|[1-9][0-9]{0,6})(?:[.,][0-9]{1,2})?\Z", re.ASCII)
STOCK_RE=re.compile(r"(?:0|[1-9][0-9]{0,5})\Z", re.ASCII)


def parse_product_csv(raw: bytes) -> list[dict]:
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_CSV_BYTES:
        raise CommerceError("csv_size_invalid",413)
    try:
        text=raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise CommerceError("csv_encoding_invalid") from exc
    if "\x00" in text:
        raise CommerceError("csv_invalid_content")
    try:
        reader=csv.reader(StringIO(text,newline=""),delimiter=";",strict=True)
        header=next(reader,None)
        if header is None or tuple(c.strip() for c in header)!=COLUMNS:
            raise CommerceError("csv_header_invalid")
        output=[]
        skus=set()
        for fields in reader:
            if not fields or (len(fields)==1 and not fields[0].strip()):
                continue
            if len(fields)!=len(COLUMNS):
                raise CommerceError("csv_row_columns_invalid")
            if len(output)>=100:
                raise CommerceError("csv_row_limit")
            raw_product=dict(zip(COLUMNS,(cell.strip() for cell in fields)))
            price=raw_product["price_try"].replace(",",".")
            if not PRICE_RE.fullmatch(raw_product["price_try"]):
                raise CommerceError("csv_price_invalid")
            price_cents=int(Decimal(price)*100)
            if price_cents<=0 or price_cents>100_000_000:
                raise CommerceError("csv_price_invalid")
            stock=raw_product["stock"]
            if not STOCK_RE.fullmatch(stock) or int(stock)>100000:
                raise CommerceError("csv_stock_invalid")
            active=raw_product["active"].lower()
            if active not in ("1","0"):
                raise CommerceError("csv_active_invalid")
            entry=validate_product({
                "sku":raw_product["sku"],
                "name":raw_product["name"],
                "category":raw_product["category"],
                "description":raw_product["description"],
                "price_cents":price_cents,
                "stock":int(stock),
                "active":active=="1"
            })
            if entry["sku"] in skus:
                raise CommerceError("import_duplicate_sku",409)
            skus.add(entry["sku"])
            output.append(entry)
    except csv.Error as exc:
        raise CommerceError("csv_parse_invalid") from exc
    if not output:
        raise CommerceError("csv_empty")
    return output
