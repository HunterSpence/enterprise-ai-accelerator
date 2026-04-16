# InventoryService

A lightweight warehouse inventory tracking REST API built with Flask and SQLAlchemy.

## Features

- Track products, warehouses, and stock movements
- REST API with JSON responses
- SQLite (dev) / PostgreSQL (prod) via SQLAlchemy ORM
- React frontend for warehouse dashboard

## Quick Start

```bash
pip install -r requirements.txt
export FLASK_APP=app.py
flask run
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/products` | List all products |
| GET | `/api/v1/products/<id>` | Get product detail |
| POST | `/api/v1/products` | Create product |
| GET | `/api/v1/warehouses` | List warehouses |
| GET | `/api/v1/warehouses/<id>` | Get warehouse |
| POST | `/api/v1/movements` | Record stock movement |

## Running Tests

```bash
pytest tests/ -v
```

## Docker

```bash
docker build -t inventory-service .
docker run -p 5000:5000 inventory-service
```

> **Note:** Pinned dependency versions in `requirements.txt` and `package.json`
> are intentionally old for demo/scanning purposes. In production always use
> current patched releases.
