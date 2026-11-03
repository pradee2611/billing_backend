import logging

import gspread
from django.conf import settings
from django.utils import timezone

from config.mongo import get_db

from .repository import amounts, order_number

log = logging.getLogger(__name__)

SHEET_TAB = "Orders"
HEADER = ["Date", "Time", "Order No.", "Customer", "Phone", "Payment", "Items", "Order Total", "Less (Round Off)", "Amount Received", "Cash Paid", "GPay Paid"]
ORDER_NO_COLUMN = 3
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def is_configured():
    return bool(settings.GOOGLE_SHEET_ID) and settings.GOOGLE_SERVICE_ACCOUNT_FILE.exists()


def _worksheet():
    client = gspread.service_account(filename=str(settings.GOOGLE_SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    book = client.open_by_key(settings.GOOGLE_SHEET_ID)
    try:
        sheet = book.worksheet(SHEET_TAB)
        current = sheet.row_values(1)
        if current != HEADER:
            # Blank out any leftover cells from an older, wider header.
            sheet.update(values=[HEADER + [""] * max(0, len(current) - len(HEADER))], range_name="A1")
        return sheet
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(SHEET_TAB, rows=1000, cols=len(HEADER))
        sheet.append_row(HEADER)
        return sheet


def rows_for(order):
    """One row per bill: who paid, how much, and every item on it (one item per line in the cell)."""
    local = timezone.localtime(order["created_at"])
    cash, gpay = amounts(order)
    items = "\n".join(
        f'{item["product_name"]} x {item["quantity"]} @ {item["unit_price"]} = {item["line_total"]}'
        for item in order["items"]
    )
    return [
        [
            local.strftime("%Y-%m-%d"),
            local.strftime("%H:%M"),
            order_number(order["_id"]),
            order.get("customer_name", ""),
            order.get("customer_phone", ""),
            order["payment_mode"],
            items,
            float(order["total"]),
            float(order.get("less_amount", "0")),
            float(order.get("payable", order["total"])),
            float(cash),
            float(gpay),
        ]
    ]


def _remove_rows(sheet, number):
    """Delete every row of one bill, bottom-up so row numbers stay valid."""
    rows = [i for i, value in enumerate(sheet.col_values(ORDER_NO_COLUMN), start=1) if value == number]
    blocks = []
    for row in rows:
        if blocks and row == blocks[-1][1] + 1:
            blocks[-1][1] = row
        else:
            blocks.append([row, row])
    for start, end in reversed(blocks):
        sheet.delete_rows(start, end)


def sync_order(order):
    """Make the sheet match the bill: remove its old rows, then append the current ones unless it was
    deleted. Safe to repeat. Returns True on success; on failure the bill stays flagged unsynced so
    `sync_sheets` can retry it."""
    try:
        sheet = _worksheet()
        _remove_rows(sheet, order_number(order["_id"]))
        if not order.get("deleted"):
            sheet.append_rows(rows_for(order), value_input_option="USER_ENTERED")
        get_db().orders.update_one({"_id": order["_id"]}, {"$set": {"sheet_synced": True}})
        return True
    except Exception:
        log.exception("Google Sheets sync failed for order %s", order["_id"])
        return False
