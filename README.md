# Billing Backend

Django REST API for the Friends Crackers billing app. It serves the product catalog, stores orders in MongoDB, and mirrors every order to a Google Sheet.

The React client lives in [`billing_frontend`](../billing_frontend).

## Tech stack

- Python 3.11, Django 5, Django REST Framework
- MongoDB (via `pymongo`) for products and orders
- Google Sheets (via `gspread`) as an order ledger
- `django-cors-headers`, `python-dotenv`
- `mongomock` for tests

SQLite (`db.sqlite3`) is only used for Django's own tables (admin, sessions). Business data is in MongoDB.

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
cp .env.example .env           # then fill in the values
python manage.py migrate
python manage.py load_products
python manage.py runserver
```

The API is served at http://127.0.0.1:8000/api/.

## Configuration

Set these in `.env`:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | MongoDB connection string (local or Atlas) |
| `MONGODB_DB` | Database name (default `crackers`) |
| `APP_USERNAME`, `APP_PASSWORD` | The single login for the app. If either is empty, nobody can sign in |
| `DJANGO_SECRET_KEY` | Secret key. Set a real value outside development |
| `DJANGO_DEBUG` | `1` (default) or `0` |
| `GOOGLE_SHEET_ID` | ID of the Google Sheet to mirror orders to (optional) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to the service-account key, relative to this folder (default `google-service-account.json`) |

### Google Sheets (optional)

1. Create a Google Cloud service account and download its JSON key into this folder.
2. Share the target sheet with the service account's email, with editor access.
3. Set `GOOGLE_SHEET_ID` in `.env`.

Orders are written to an `Orders` tab, which is created if missing. If Sheets isn't configured, syncing is skipped.

Never commit the key file or `.env`. Both are in `.gitignore`.

## API

All endpoints except login need an `Authorization: Bearer <token>` header. Tokens last 7 days.

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/auth/login/` | Exchange username and password for a token (limited to 10 requests per minute) |
| GET | `/api/products/` | List active products |
| GET | `/api/orders/` | Orders grouped by date, newest first, with a total per date |
| POST | `/api/orders/` | Create an order |
| GET | `/api/orders/<id>/` | Order detail |
| PUT | `/api/orders/<id>/` | Replace an order |
| DELETE | `/api/orders/<id>/` | Delete an order |

An order has a `payment_mode`, a non-empty `items` list (`product` and `quantity` from 1 to 10000), and optional `less_amount`, `cash_amount`, `customer_name` and a 10-digit `customer_phone`.

## Management commands

```bash
python manage.py load_products [path/to/file.csv]   # upsert products from CSV
python manage.py sync_sheets [--all]                # push unsynced orders to Google Sheets
```

`load_products` reads `data/crackers.csv` by default, with columns `code,category,name,name_ta,mrp,price`. Products missing from the file are marked inactive instead of deleted.

`sync_sheets` pushes orders that aren't in the sheet yet, for example after an outage. `--all` re-pushes everything.

## Tests

```bash
python manage.py test
```

## Project layout

```
config/    settings, URLs, login, token auth, Mongo connection
catalog/   products: repository, serializers, views, load_products command
orders/    orders: repository, services, serializers, views, Sheets sync
data/      crackers.csv product list
```
