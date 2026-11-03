from rest_framework import serializers

from . import repository


class ActiveProductField(serializers.Field):
    """Accepts a product id string and resolves it to an active product document."""

    default_error_messages = {"not_found": "Unknown or inactive product."}

    def to_internal_value(self, data):
        product = repository.get_active(str(data))
        if product is None:
            self.fail("not_found")
        return product

    def to_representation(self, value):
        return str(value["_id"])
