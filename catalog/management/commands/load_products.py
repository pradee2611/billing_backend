import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo import UpdateOne

from config.mongo import get_db


class Command(BaseCommand):
    help = "Create or update products in MongoDB from a CSV with code,category,name,name_ta,mrp,price columns."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=settings.BASE_DIR / "data" / "crackers.csv")

    def handle(self, *args, path, **options):
        with Path(path).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        products = {}
        for number, row in enumerate(rows, start=2):
            name = row["name"].strip()
            try:
                products[int(row["code"])] = {
                    "category": row["category"].strip(),
                    "name": name,
                    "name_ta": row["name_ta"].strip(),
                    "mrp": str(Decimal(row["mrp"]).quantize(Decimal("0.01"))),
                    "price": str(Decimal(row["price"]).quantize(Decimal("0.01"))),
                }
            except (InvalidOperation, ValueError, KeyError):
                raise CommandError(f"Row {number} ({name!r}): invalid code or price")

        db = get_db()
        db.products.bulk_write(
            [
                UpdateOne({"code": code}, {"$set": {**fields, "is_active": True}}, upsert=True)
                for code, fields in products.items()
            ]
        )
        db.products.update_many({"code": {"$nin": list(products)}}, {"$set": {"is_active": False}})
        active = db.products.count_documents({"is_active": True})
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(products)} products ({active} active)"))
