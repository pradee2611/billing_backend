import logging
import os

from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Keep the product catalog in sync with data/crackers.csv on every start (i.e. every deploy).
# load_products is idempotent; a failure is logged but must never stop the API from serving.
if os.environ.get("AUTO_LOAD_PRODUCTS", "1") == "1":
    try:
        call_command("load_products")
    except Exception:
        logging.getLogger(__name__).exception("Auto-loading products failed")
