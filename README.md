# Smart Supermarket Billing System

A production-style Django supermarket billing and inventory system with dashboard analytics, POS billing, PDF invoices, barcode generation, stock alerts, CRUD modules, reports, and demo data.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/`.

Demo admin login:

```text
Username: admin
Password: admin12345
```

## Modules

- Dashboard with business cards, sales charts, product/category/customer analytics, and recent activity.
- POS billing with barcode input, camera scanning via html5-qrcode, product search, cart quantities, discounts, tax/GST, PDF invoice, print flow, and WhatsApp message link.
- Product management with images, stock levels, auto/manual barcode, generated barcode images, and CRUD.
- Customer management with purchase totals and invoice history.
- Sales history with filters, invoice detail, print, and PDF download.
- Reports with daily/weekly/monthly totals and CSV, Excel, PDF exports.
- Analytics powered by Pandas for revenue trends, product performance, customer growth, category distribution, and profit.
- Stock alerts with healthy, low, and critical indicators plus reorder suggestions.
- Settings for shop name, address, GST, contact details, invoice footer, and company logo.

SQLite is configured for development. To move to MySQL later, replace `DATABASES` in `smartbilling/settings.py` with a MySQL backend and install the appropriate database driver.
