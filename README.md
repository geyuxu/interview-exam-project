# Order Details, Tracking and Shipping Estimates

Python / FastAPI + Vue 3 / TypeScript / Vite. Browse orders, match products, calculate GST, track multiple shipments and import order JSON files.

## Features

- Search by order number, customer or SKU, with product details, contacts, delivery addresses and totals.
- A snapshot of real product query results covering nine SKUs, including names, descriptions, prices and packaging specifications.
- Server-side Australia Post / StarTrack test API integration with status and events, plus handling for timeouts, authentication failures and missing records.
- Downloadable order template, JSON import, field validation and cross-order relationship checks. Imported orders also support carrier tracking.
- Optional shipping estimates, disabled by default. Product images are neutral placeholders. TNT is not integrated and its shipping fee is A$0.00.
- Desktop and mobile layouts, retry controls and temporary imports that stay in the current page.

## Run locally

Requirements: Python 3.11+, Node.js 22.12+ (22.x) or 24+, npm and Git.

```powershell
git clone https://github.com/geyuxu/interview-exam-project.git
cd interview-exam-project
```

Start the services in two terminals, each initially at the repository root.

### Backend (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Enter carrier test credentials in your local `backend/.env`. Without credentials, order browsing, imports and calculations still work; tracking displays a configuration notice. In PyCharm, select `backend/.venv/Scripts/python.exe` as the interpreter. On macOS / Linux, use `.venv/bin/python` and copy the initial configuration with `cp -n .env.example .env`.

Health check: <http://127.0.0.1:8000/api/health>. Interactive API documentation: <http://127.0.0.1:8000/docs>.

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. The development server proxies `/api` to port 8000. Override the target with the server-side `API_PROXY_TARGET` environment variable. The lockfile uses npm mirror URLs and integrity hashes; global npm settings are unchanged.

Production deployment requires static file hosting and an `/api` reverse proxy. The current application is intended for local use and does not implement login or production access controls.

## Data

The product catalogue comes from the SQL query service's `product_list` table:

```sql
SELECT * FROM product_list
WHERE SKU IN ('TBAMET10','TBAMET28','TBOPAL28','AURPUR10','HARNIG','LELCBD100','HALGEO15','MCMW10','MCBO30');
```

`backend/data/products.json` contains the nine complete records returned by the actual query. `backend/data/source.json` records the query endpoint, SQL, retrieval time and row count. This is a database query snapshot; the running application does not connect to the database in real time. To update it, rerun the query, replace the complete results and update the source metadata.

`backend/data/orders.json` holds the initial orders and shipment relationships, and is served as the downloadable template. Product names and specifications are displayed as returned, without inferring them from SKUs. Simulated tracking responses exist only in automated tests; the application queries the actual carrier API.

### Import structure

| Collection | Required fields |
|---|---|
| `orders` | `order_no`, `order_date` (YYYY-MM-DD), `status`, `company`, `customer`, `phone`, `email`, `address`, `postcode` |
| `shipments` | `id`, `order_no`, `carrier` (startrack/auspost/tnt), `tracking_no` |
| `line_items` | `order_no`, `sku`, `quantity`, `shipment_id` |

Order numbers and shipment IDs must each be unique. Quantities must be integers from 1 to 100000, and postcodes must contain four digits. Each order and shipment must have at least one line item. A line item's shipment must belong to the same order.

Imports support up to 100 orders, 500 shipments and 2000 line items. Both frontend and backend enforce a 1 MiB limit. UTF-8 BOM is supported. Unknown fields, invalid quantities, duplicate IDs and invalid relationships are rejected. Imported content is not persisted.

If a SKU cannot be matched or its price is invalid, other available information remains visible, but the affected order's Subtotal, GST and Total are marked unavailable. Other orders calculate normally.

## Amounts and shipping

All amounts are in AUD. RRP includes 10% GST:

```text
Unit price excluding GST = RRP / 1.10
Line amount excluding GST = Unit price excluding GST × Quantity
Order subtotal excluding GST = Sum of this order's line amounts excluding GST
GST = Order subtotal excluding GST × 10%
Total = Subtotal excluding GST + GST + Shipping
```

The backend uses Decimal without premature rounding. Displayed amounts use ROUND_HALF_UP to two decimal places. The total adds the rounded subtotal, GST and shipping fee. The sum of displayed line amounts may differ from the overall subtotal by a cent; the API returns `rounding_adjustment` and the page explains it. This is not an extra charge. Input prices must be non-negative, finite and precise to whole cents.

Reference totals for the current product snapshot, excluding shipping:

| Order | Subtotal ex GST | GST | Total |
|---|---:|---:|---:|
| PO-20251130-00072 | A$1,937.27 | A$193.73 | A$2,131.00 |
| PO-20251203-00046 | A$1,504.55 | A$150.45 | A$1,655.00 |

Shipping estimates are disabled by default. When enabled, each shipment is calculated separately using the following illustrative rules, which are not carrier quotes:

1. Convert product weights to kg and volumes to cm³, multiply by quantity and sum each. Derive volume from dimensions if no volume is available.
2. Add 0.2 kg of packaging weight and a 20% packaging allowance to the volume.
3. Chargeable weight is `max(product weight + 0.2, product volume × 1.2 / 5000)`, rounded up to a whole kg.
4. The shipment fee is A$8 + A$2.50 × chargeable weight + a postcode surcharge. Origin postcode is 2111; destinations whose first digit is not 2 incur an A$3 surcharge.
5. Missing or invalid specifications, or TNT shipments, produce an A$0.00 fee with an explanation.

The ambiguous `Volumetric_GrossWeight` field is not used. Shipping is added as a final amount, while product GST is calculated separately. Each of the two initial orders adds A$16.00 when estimates are enabled.

## Tracking integration

```text
GET https://digitalapi.auspost.com.au/test/shipping/v1/track?tracking_ids=...
Authorization: Basic <encoded API key and password>
Account-Number: <account for the carrier product>
Content-Type: application/json
Accept: application/json
```

Credentials are read only on the backend. Process environment variables take precedence over `.env`:

| Environment variable | Purpose |
|---|---|
| `AUSPOST_API_KEY` | API key |
| `AUSPOST_API_PASSWORD` | API password |
| `STARTRACK_ACCOUNT_NUMBER` | StarTrack product account |
| `AUSPOST_ACCOUNT_NUMBER` | Australia Post product account |

Accounts remain strings to preserve leading zeros. Requests use only the testbed, with a 10-second timeout and a limit of 10 external queries per minute per process. Results for the same consignment are cached for 60 seconds. Credential changes invalidate the old cache. Duplicate in-flight queries are prevented without blocking other consignments' network requests. Multiple server processes require a shared cache and rate limiter.

Results strictly match `tracking_id` and read parcel status and events. Event timestamps retain their original format. Test environment results are labelled accordingly. Failures expose only safe messages, HTTP status and error codes, without credentials or complete upstream responses.

**Current integration limits:** Actual requests on 2026-09-22 returned HTTP 401 / `API_001` (authentication failure). The testbed `/shipments` endpoint returned the same error. Valid test credentials or restored carrier authorisation are required to verify successful tracking. The UI retains an unavailable state and retry controls. TNT Australia domestic tracking is not integrated, with shipping set to zero.

## API and structure

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service health check |
| GET | `/api/orders?estimate=false` | Initial orders and calculated totals |
| GET | `/api/orders/template` | Download the JSON import template |
| POST | `/api/orders/preview?estimate=false` | Validate and calculate imported orders |
| GET | `/api/shipments/{shipment_id}/tracking` | Track a shipment from the initial orders |
| POST | `/api/tracking` | Track by `carrier` and `tracking_no`, including imported orders |

Validation failures return 422, oversized requests return 413, and unreadable local data returns 503. Carrier failures return HTTP 200 with an explicit `unavailable` business state; `http_status` contains the upstream carrier status. The frontend validates response structures with Zod before updating the page.

```text
backend/app/models.py        Input and relationship validation
backend/app/orders.py        Product matching, amounts and shipping
backend/app/tracking.py      Carrier adapter, cache and rate limit
backend/app/middleware.py    Request size limit
backend/app/main.py          Routes and configuration
backend/data/               Orders, product snapshot and source metadata
backend/tests/              Backend regression tests
frontend/src/App.vue         Page and interactions
frontend/src/contracts.ts    Response validation and types
frontend/tests/              Desktop and mobile browser tests
.github/workflows/ci.yml     Automated checks
```

## Tests

Run from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m ruff check backend
.\backend\.venv\Scripts\python.exe -m ruff format --check backend
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm ci
npm run format:check
npm run build
npx playwright install chromium
npm run test:e2e
```

To use an installed Edge browser instead, set `$env:PLAYWRIGHT_CHANNEL = 'msedge'` before running browser tests. Tests start an isolated backend on port 8011 and frontend on port 5181; keep these ports available.

Coverage includes calculations and rounding, relationships, upload limits, corrupt data, authentication requests and failures, caching and concurrency. Browser tests cover desktop and mobile order selection, search, template download, imports, shipping, tracking and error recovery. Test processes disable local carrier credentials; tracking fixtures exist only in tests. There are 51 backend tests and 10 browser tests. Backend test dependencies currently emit two third-party deprecation warnings.

GitHub Actions runs backend checks, frontend formatting and builds, and Chromium browser tests on pushes and pull requests.

## Repository and configuration

Repository: [geyuxu/interview-exam-project](https://github.com/geyuxu/interview-exam-project). Git ignores `.env`, virtual environments, dependencies, build outputs and test reports. Only the credential-free `.env.example` is committed.

API references: [Australia Post Track Items](https://developers.auspost.com.au/content/apis/shipping-and-tracking/reference-track-items.html) and [Test environment and authentication FAQ](https://developers.auspost.com.au/content/apis/shipping-and-tracking/info/api-resources/faq.html).
