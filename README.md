# Stock Management API

A small FastAPI service for managing products, warehouses, and stock levels.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

The API is then available at http://localhost:8000, with interactive docs at
http://localhost:8000/docs.

Two warehouses (`Paris warehouse`, `Lyon warehouse`) are seeded automatically
on first run.

## Endpoints

- `POST /products` — create a product
- `GET /products` — list products with total stock across all warehouses
- `GET /products/low-stock?margin=0.3` — list products at or under the
  reorder threshold; `margin` (default `0`) widens that to also include
  products within X% above threshold
- `POST /stocks/adjustments` — record a stock movement (positive to add,
  negative to remove)
- `POST /stocks/transfers` — move stock between warehouses
- `GET /stocks/transfers` — transfer history, most recent first

## Stock transfers

`POST /stocks/transfers` runs two `adjust_stock` calls (out of source, into
destination) in one transaction, then links the resulting movement IDs in a
`TransferHistory` row:

```json
{
  "product_id": 1,
  "source_warehouse_id": 1,
  "destination_warehouse_id": 2,
  "quantity": 5,
  "reason": "Rebalancing stock"
}
```

`400` if source == destination, `404` if product/warehouse doesn't exist,
`409` if source doesn't have enough stock.

`GET /stocks/transfers` reads that history back, with a description
generated on the fly from each linked movement (not stored as text).

## Tests

```bash
pytest -v          # or -s to see response bodies via the `show` fixture
```

21 tests in `tests/`, one file per adjustment. `conftest.py`'s `client`
fixture resets the DB per test so warehouse ids are always `1`/`2`.

## Project layout

```
app/
├── main.py        # FastAPI app, table creation, warehouse seeding
├── database.py    # SQLAlchemy engine, session, get_db dependency
├── logging_config.py  # Logging setup
├── models.py      # SQLAlchemy ORM models
├── schemas.py     # Pydantic request/response schemas
├── services.py    # Business logic (ProductService, StockService)
└── routers.py     # HTTP endpoints
tests/              # pytest suite
```