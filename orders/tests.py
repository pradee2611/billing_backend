from decimal import Decimal
from unittest import mock

import mongomock
from django.test import SimpleTestCase, override_settings

from config import mongo


from config.authentication import make_token


@override_settings(APP_USERNAME="friends", APP_PASSWORD="test-password-123")
class OrderApiTests(SimpleTestCase):
    def setUp(self):
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {make_token('friends')}"
        mongo._db = mongomock.MongoClient(tz_aware=True).crackers
        self.addCleanup(setattr, mongo, "_db", None)
        db = mongo._db
        self.sparkler = str(db.products.insert_one({"code": 1, "category": "Sparklers", "name": "Sparkler", "name_ta": "", "mrp": "200.00", "price": "40.00", "is_active": True}).inserted_id)
        self.rocket = str(db.products.insert_one({"code": 2, "category": "Rocket", "name": "Rocket", "name_ta": "", "mrp": "550.00", "price": "110.00", "is_active": True}).inserted_id)
        patcher = mock.patch("orders.sheets.is_configured", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def place(self, mode="CASH", items=None, **extra):
        if items is None:
            items = [{"product": self.sparkler, "quantity": 2}, {"product": self.rocket, "quantity": 1}]
        return self.client.post("/api/orders/", {"payment_mode": mode, "items": items, **extra}, content_type="application/json")

    def test_create_order_calculates_total(self):
        response = self.place("GPAY")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.json()["total"]), Decimal("190"))
        self.assertEqual(response.json()["number"], "ORD-0001")
        self.assertEqual(len(response.json()["items"]), 2)
        self.assertEqual(Decimal(response.json()["savings"]), Decimal("760"))

    def test_rejects_empty_cart_bad_mode_and_unknown_product(self):
        self.assertEqual(self.place(items=[]).status_code, 400)
        self.assertEqual(self.place(mode="CARD").status_code, 400)
        self.assertEqual(self.place(items=[{"product": "nope", "quantity": 1}]).status_code, 400)

    def test_customer_details_saved_and_validated(self):
        data = self.place(customer_name=" Ravi ", customer_phone="9876543210").json()
        self.assertEqual((data["customer_name"], data["customer_phone"]), ("Ravi", "9876543210"))
        self.assertEqual(self.place(customer_phone="12345").status_code, 400)
        self.assertEqual(self.place().json()["customer_phone"], "")

    def test_duplicate_lines_are_merged(self):
        response = self.place(items=[{"product": self.rocket, "quantity": 1}, {"product": self.rocket, "quantity": 2}])
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(Decimal(response.json()["total"]), Decimal("330"))

    def test_list_is_grouped_by_date_with_total_and_detail(self):
        self.place()
        order_id = self.place().json()["id"]
        groups = self.client.get("/api/orders/").json()
        self.assertEqual(len(groups), 1)
        self.assertEqual(Decimal(groups[0]["total"]), Decimal("380"))
        self.assertEqual(len(groups[0]["orders"]), 2)
        self.assertEqual(self.client.get(f"/api/orders/{order_id}/").status_code, 200)
        self.assertEqual(self.client.get("/api/orders/999/").status_code, 404)

    def test_product_search_by_name_and_code(self):
        self.assertEqual([p["code"] for p in self.client.get("/api/products/?search=2").json()], [2])
        names = [p["name"] for p in self.client.get("/api/products/?search=rock").json()]
        self.assertEqual(names, ["Rocket"])

    def put(self, order_id, items, mode="GPAY", **extra):
        body = {"payment_mode": mode, "items": items, **extra}
        return self.client.put(f"/api/orders/{order_id}/", body, content_type="application/json")

    def test_edit_keeps_number_and_original_price(self):
        order = self.client.get(f"/api/orders/{self.place().json()['id']}/").json()
        mongo._db.products.update_one({"code": 1}, {"$set": {"price": "99.00"}})  # price changes later
        edited = self.put(order["id"], [{"product": self.sparkler, "quantity": 5}], customer_name="Mani")
        self.assertEqual(edited.status_code, 200)
        data = edited.json()
        self.assertEqual((data["number"], data["created_at"]), (order["number"], order["created_at"]))
        self.assertEqual(Decimal(data["total"]), Decimal("200"))  # 5 x 40, not 5 x 99
        self.assertEqual((data["payment_mode"], data["customer_name"]), ("GPAY", "Mani"))
        self.assertEqual(self.put(999, [{"product": self.rocket, "quantity": 1}]).status_code, 404)
        self.assertEqual(self.put(order["id"], []).status_code, 400)

    def test_delete_hides_bill_but_keeps_record(self):
        keep = self.place().json()["id"]
        gone = self.place().json()["id"]
        self.assertEqual(self.client.delete(f"/api/orders/{gone}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/orders/{gone}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/orders/{gone}/").status_code, 404)
        groups = self.client.get("/api/orders/").json()
        self.assertEqual([o["id"] for o in groups[0]["orders"]], [keep])
        self.assertEqual(Decimal(groups[0]["total"]), Decimal("190"))
        self.assertTrue(mongo._db.orders.find_one({"_id": gone})["deleted"])
        self.assertEqual(self.place().json()["number"], "ORD-0003")

    def test_split_payment(self):
        data = self.place("SPLIT", cash_amount="100").json()
        self.assertEqual((data["payment_mode"], data["cash_amount"], data["gpay_amount"]), ("SPLIT", "100.00", "90.00"))
        for bad in (None, "0", "190", "250"):
            extra = {} if bad is None else {"cash_amount": bad}
            self.assertEqual(self.place("SPLIT", **extra).status_code, 400, bad)
        single = self.place("GPAY", cash_amount="50").json()  # stray cash amount is ignored
        self.assertEqual((single["cash_amount"], single["gpay_amount"]), ("0.00", "190.00"))
        groups = self.client.get("/api/orders/").json()
        self.assertEqual(groups[0]["by_payment"], {"CASH": "100.00", "GPAY": "280.00"})

    def test_edit_to_split_and_back(self):
        order_id = self.place("CASH").json()["id"]
        items = [{"product": self.sparkler, "quantity": 2}, {"product": self.rocket, "quantity": 1}]
        edited = self.put(order_id, items, mode="SPLIT", cash_amount="40").json()
        self.assertEqual((edited["cash_amount"], edited["gpay_amount"]), ("40.00", "150.00"))
        self.assertEqual(self.put(order_id, items, mode="SPLIT").status_code, 400)
        back = self.put(order_id, items, mode="CASH").json()
        self.assertEqual((back["cash_amount"], back["gpay_amount"]), ("190.00", "0.00"))

    def test_less_round_off_is_tracked(self):
        data = self.place("CASH", less_amount="40").json()
        self.assertEqual((data["total"], data["less_amount"], data["payable"]), ("190.00", "40.00", "150.00"))
        self.assertEqual((data["cash_amount"], data["gpay_amount"]), ("150.00", "0.00"))
        self.assertEqual(self.place(less_amount="190").status_code, 400)
        self.assertEqual(self.place(less_amount="-5").status_code, 400)
        self.assertEqual(self.place().json()["payable"], "190.00")
        groups = self.client.get("/api/orders/").json()
        self.assertEqual(groups[0]["total"], "340.00")  # 150 + 190 actually collected

    def test_split_applies_to_payable_after_less(self):
        data = self.place("SPLIT", cash_amount="100", less_amount="40").json()
        self.assertEqual((data["cash_amount"], data["gpay_amount"]), ("100.00", "50.00"))
        self.assertEqual(self.place("SPLIT", cash_amount="150", less_amount="40").status_code, 400)

    def test_edit_can_change_less(self):
        order_id = self.place(less_amount="40").json()["id"]
        items = [{"product": self.sparkler, "quantity": 2}, {"product": self.rocket, "quantity": 1}]
        self.assertEqual(self.put(order_id, items, mode="CASH", less_amount="90").json()["payable"], "100.00")
        self.assertEqual(self.put(order_id, items, mode="CASH").json()["payable"], "190.00")

    def test_api_requires_login(self):
        self.client.defaults.pop("HTTP_AUTHORIZATION")
        for path in ("/api/orders/", "/api/products/", "/api/orders/1/"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.place().status_code, 401)
        self.client.defaults["HTTP_AUTHORIZATION"] = "Bearer not-a-real-token"
        self.assertEqual(self.client.get("/api/orders/").status_code, 401)

    def test_login(self):
        self.client.defaults.pop("HTTP_AUTHORIZATION")
        post = lambda u, p: self.client.post("/api/auth/login/", {"username": u, "password": p}, content_type="application/json")
        for bad in (("friends", "wrong"), ("Friends", "test-password-123"), ("admin", "test-password-123"), ("friends", "")):
            self.assertEqual(post(*bad).status_code in (400, 401), True, bad)
        good = post("friends", "test-password-123")
        self.assertEqual(good.status_code, 200)
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {good.json()['token']}"
        self.assertEqual(self.client.get("/api/orders/").status_code, 200)

    def test_empty_configured_password_blocks_login(self):
        with override_settings(APP_USERNAME="", APP_PASSWORD=""):
            self.client.defaults.pop("HTTP_AUTHORIZATION")
            response = self.client.post("/api/auth/login/", {"username": "", "password": ""}, content_type="application/json")
            self.assertEqual(response.status_code in (400, 401), True)

    def test_changing_password_invalidates_old_tokens(self):
        with override_settings(APP_PASSWORD="new-password"):
            self.assertEqual(self.client.get("/api/orders/").status_code, 401)

    def test_sheet_rows_one_per_item(self):
        from orders import sheets

        order = mongo._db.orders.find_one({"_id": self.place().json()["id"]})
        rows = sheets.rows_for(order)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][2], "ORD-0001")
        self.assertEqual(rows[0][9:], [190.0, "", "", 190.0, 0.0, 0.0, 190.0])
