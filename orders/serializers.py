from rest_framework import serializers

from catalog.serializers import ActiveProductField

from .repository import PAYMENT_MODES


class OrderLineInputSerializer(serializers.Serializer):
    product = ActiveProductField()
    quantity = serializers.IntegerField(min_value=1, max_value=10000)


class OrderCreateSerializer(serializers.Serializer):
    payment_mode = serializers.ChoiceField(choices=PAYMENT_MODES)
    items = OrderLineInputSerializer(many=True, allow_empty=False)
    less_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True, default=None)
    cash_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True, default=None)
    customer_name = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    customer_phone = serializers.RegexField(
        r"^\d{10}$", required=False, allow_blank=True, default="",
        error_messages={"invalid": "Enter a 10-digit mobile number."},
    )
