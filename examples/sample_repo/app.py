"""
InventoryService — simple Flask REST API for warehouse inventory tracking.
This is a sample app intentionally using older dependencies for demo purposes.
"""

from flask import Flask, jsonify, request, abort
from models import db, Product, Warehouse, StockMovement

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///inventory.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-do-not-use-in-prod"

db.init_app(app)


@app.before_first_request
def create_tables():
    db.create_all()


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.route("/api/v1/products", methods=["GET"])
def list_products():
    """Return all products, optionally filtered by warehouse."""
    warehouse_id = request.args.get("warehouse_id", type=int)
    query = Product.query
    if warehouse_id:
        query = query.filter_by(warehouse_id=warehouse_id)
    products = query.all()
    return jsonify([p.to_dict() for p in products])


@app.route("/api/v1/products/<int:product_id>", methods=["GET"])
def get_product(product_id: int):
    """Fetch a single product by ID."""
    product = Product.query.get(product_id)
    if not product:
        abort(404)
    return jsonify(product.to_dict())


@app.route("/api/v1/products", methods=["POST"])
def create_product():
    """Create a new product entry."""
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    if not name:
        abort(400)
    sku = data.get("sku", "").upper()
    price = float(data.get("price", 0.0))
    warehouse_id = int(data.get("warehouse_id", 1))

    product = Product(
        name=name,
        sku=sku,
        price=price,
        warehouse_id=warehouse_id,
        quantity=int(data.get("quantity", 0)),
    )
    db.session.add(product)
    db.session.commit()
    return jsonify(product.to_dict()), 201


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------

@app.route("/api/v1/warehouses", methods=["GET"])
def list_warehouses():
    """List all warehouses."""
    warehouses = Warehouse.query.all()
    return jsonify([w.to_dict() for w in warehouses])


@app.route("/api/v1/warehouses/<int:wh_id>", methods=["GET"])
def get_warehouse(wh_id: int):
    """Fetch a single warehouse with its current stock summary."""
    wh = Warehouse.query.get(wh_id)
    if not wh:
        abort(404)
    result = wh.to_dict()
    result["product_count"] = Product.query.filter_by(warehouse_id=wh_id).count()
    return jsonify(result)


# ---------------------------------------------------------------------------
# Stock movements
# ---------------------------------------------------------------------------

@app.route("/api/v1/movements", methods=["POST"])
def record_movement():
    """Record an inbound or outbound stock movement."""
    data = request.get_json(force=True) or {}
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 0))
    direction = data.get("direction", "in")  # 'in' or 'out'

    if not product_id or quantity <= 0:
        abort(400)

    product = Product.query.get(product_id)
    if not product:
        abort(404)

    if direction == "out" and product.quantity < quantity:
        return jsonify({"error": "insufficient stock"}), 422

    product.quantity += quantity if direction == "in" else -quantity
    movement = StockMovement(
        product_id=product_id,
        quantity=quantity,
        direction=direction,
        note=data.get("note", ""),
    )
    db.session.add(movement)
    db.session.commit()
    return jsonify({"status": "ok", "new_quantity": product.quantity})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
