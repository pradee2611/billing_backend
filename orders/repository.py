from collections import defaultdict
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.utils import timezone
from pymongo import ReturnDocument
from rest_framework.exceptions import ValidationError

from config.mongo import get_db

PAYMENT_MODES = ("CASH", "GPAY", "SPLIT")
LIVE = {"deleted": {"$ne": True}}


def next_number():
    counter = get_db().counters.find_one_and_update(
        {"_id": "orders"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return counter["seq"]


def order_number(order_id):
    return f"ORD-{order_id:04d}"


def amounts(order):
    """(cash, gpay) paid on a bill. Bills saved before split payments derive them from the mode."""
    if "cash_amount" in order:
        return order["cash_amount"], order["gpay_amount"]
    zero = "0.00"
    payable = order.get("payable", order["total"])
    return (payable, zero) if order["payment_mode"] == "CASH" else (zero, payable)


def apply_less(total, less_amount):
    """A round-off or discount given on the bill. Returns (less, payable) strings; payable stays above 0."""
    total = Decimal(total)
    less = Decimal(less_amount or 0)
    if not (0 <= less < total):
        raise ValidationError({"less_amount": f"Less must be 0 or more and below the bill total ({total})."})
    cents = Decimal("0.01")
    return str(less.quantize(cents)), str((total - less).quantize(cents))


def payment_split(payment_mode, total, cash_amount):
    """Return (cash, gpay) strings. A split needs cash strictly between 0 and the total; GPay is the rest."""
    total = Decimal(total)
    if payment_mode == "CASH":
        cash = total
    elif payment_mode == "GPAY":
        cash = Decimal("0")
    else:
        if cash_amount is None or not (0 < cash_amount < total):
            raise ValidationError({"cash_amount": f"For a split payment, cash must be more than 0 and less than the amount to pay ({total})."})
        cash = cash_amount
    cents = Decimal("0.01")
    return str(cash.quantize(cents)), str((total - cash).quantize(cents))


def summary(order):
    cash, gpay = amounts(order)
    return {
        "id": order["_id"],
        "number": order_number(order["_id"]),
        "created_at": order["created_at"].isoformat(),
        "payment_mode": order["payment_mode"],
        "total": order["total"],
        "cash_amount": cash,
        "gpay_amount": gpay,
        "less_amount": order.get("less_amount", "0.00"),
        "payable": order.get("payable", order["total"]),
        "customer_name": order.get("customer_name", ""),
        "customer_phone": order.get("customer_phone", ""),
    }


def detail(order):
    mrp_total = order.get("mrp_total", order["total"])
    return {
        **summary(order),
        "mrp_total": mrp_total,
        "savings": str(Decimal(mrp_total) - Decimal(order["total"])),
        "items": order["items"],
    }


def build_lines(items, existing=()):
    """Merge duplicate products into priced lines. A product already on the bill keeps the name and
    price it was sold at, so editing an old bill never reprices it."""
    snapshots = {line["product_id"]: line for line in existing}
    merged = {}
    for line in items:
        product = line["product"]
        key = str(product["_id"])
        if key in merged:
            merged[key]["quantity"] += line["quantity"]
        elif key in snapshots:
            old = snapshots[key]
            merged[key] = {
                "product_id": key,
                "code": old["code"],
                "product_name": old["product_name"],
                "name_ta": old.get("name_ta", ""),
                "mrp": old["mrp"],
                "unit_price": old["unit_price"],
                "quantity": line["quantity"],
            }
        else:
            merged[key] = {
                "product_id": key,
                "code": product["code"],
                "product_name": product["name"],
                "name_ta": product.get("name_ta", ""),
                "mrp": product["mrp"],
                "unit_price": product["price"],
                "quantity": line["quantity"],
            }
    lines = []
    for line in merged.values():
        line["line_total"] = str(Decimal(line["unit_price"]) * line["quantity"])
        line["mrp_total"] = str(Decimal(line["mrp"]) * line["quantity"])
        lines.append(line)
    lines.sort(key=lambda l: l["code"])
    total = sum((Decimal(l["line_total"]) for l in lines), Decimal("0"))
    mrp_total = sum((Decimal(l["mrp_total"]) for l in lines), Decimal("0"))
    return lines, str(total), str(mrp_total)


def create(payment_mode, items, customer_name="", customer_phone="", cash_amount=None, less_amount=None):
    lines, total, mrp_total = build_lines(items)
    less, payable = apply_less(total, less_amount)
    cash, gpay = payment_split(payment_mode, payable, cash_amount)
    order = {
        "_id": next_number(),
        "created_at": datetime.now(dt_timezone.utc),
        "payment_mode": payment_mode,
        "cash_amount": cash,
        "gpay_amount": gpay,
        "less_amount": less,
        "payable": payable,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "total": total,
        "mrp_total": mrp_total,
        "items": lines,
        "sheet_synced": False,
    }
    get_db().orders.insert_one(order)
    return order


def update(order_id, payment_mode, items, customer_name="", customer_phone="", cash_amount=None, less_amount=None):
    """Replace a bill's contents, keeping its number and original date. Returns None if it is gone."""
    current = get(order_id)
    if current is None:
        return None
    lines, total, mrp_total = build_lines(items, current["items"])
    less, payable = apply_less(total, less_amount)
    cash, gpay = payment_split(payment_mode, payable, cash_amount)
    return get_db().orders.find_one_and_update(
        {"_id": order_id, **LIVE},
        {
            "$set": {
                "payment_mode": payment_mode,
                "cash_amount": cash,
                "gpay_amount": gpay,
                "less_amount": less,
                "payable": payable,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "total": total,
                "mrp_total": mrp_total,
                "items": lines,
                "edited_at": datetime.now(dt_timezone.utc),
                "sheet_synced": False,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


def soft_delete(order_id):
    """Hide a bill everywhere but keep the record, so a mistaken delete can be undone in the database."""
    return get_db().orders.find_one_and_update(
        {"_id": order_id, **LIVE},
        {"$set": {"deleted": True, "deleted_at": datetime.now(dt_timezone.utc), "sheet_synced": False}},
        return_document=ReturnDocument.AFTER,
    )


def get(order_id):
    return get_db().orders.find_one({"_id": order_id, **LIVE})


def grouped_by_date():
    by_date = defaultdict(list)
    for order in get_db().orders.find(LIVE).sort([("created_at", -1), ("_id", -1)]):
        by_date[timezone.localdate(order["created_at"]).isoformat()].append(order)

    def total(orders):
        return str(sum((Decimal(o.get("payable", o["total"])) for o in orders), Decimal("0")))

    return [
        {
            "date": day,
            "total": total(orders),
            "count": len(orders),
            "by_payment": {
                "CASH": str(sum((Decimal(amounts(o)[0]) for o in orders), Decimal("0"))),
                "GPAY": str(sum((Decimal(amounts(o)[1]) for o in orders), Decimal("0"))),
            },
            "orders": [{**summary(o), "item_count": sum(i["quantity"] for i in o["items"])} for o in orders],
        }
        for day, orders in by_date.items()
    ]
