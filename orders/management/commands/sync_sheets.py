from django.core.management.base import BaseCommand, CommandError

from config.mongo import get_db
from orders import sheets


class Command(BaseCommand):
    help = "Push orders not yet in Google Sheets (e.g. after an outage). Use --all to re-push everything."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true")

    def handle(self, *args, all, **options):
        if not sheets.is_configured():
            raise CommandError("Set GOOGLE_SHEET_ID and place the service-account JSON key first.")
        query = {} if all else {"sheet_synced": {"$ne": True}}
        done = failed = 0
        for order in get_db().orders.find(query).sort("_id", 1):
            if sheets.sync_order(order):
                done += 1
            else:
                failed += 1
        self.stdout.write(self.style.SUCCESS(f"Synced {done} orders, {failed} failed"))
