import threading

from . import repository, sheets


def _push_to_sheet(order):
    if sheets.is_configured():
        threading.Thread(target=sheets.sync_order, args=(order,), daemon=True).start()


def create_order(payment_mode, items, customer_name="", customer_phone="", cash_amount=None, less_amount=None):
    order = repository.create(payment_mode, items, customer_name.strip(), customer_phone, cash_amount, less_amount)
    _push_to_sheet(order)
    return order


def update_order(order_id, payment_mode, items, customer_name="", customer_phone="", cash_amount=None, less_amount=None):
    order = repository.update(order_id, payment_mode, items, customer_name.strip(), customer_phone, cash_amount, less_amount)
    if order:
        _push_to_sheet(order)
    return order


def delete_order(order_id):
    order = repository.soft_delete(order_id)
    if order:
        _push_to_sheet(order)
    return order
