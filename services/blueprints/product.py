import os
import sys

from flask import Blueprint, request, jsonify, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.site_connector_client import SiteConnectorClient, SiteConnectorError
from database.db import init_db
from database.repository import get_wp_connection
from services.product_builder import ProductBuilder
from utils.helpers import log

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
product_bp = Blueprint("product_bp", __name__, template_folder=template_dir)

# Lazily constructed, same as the bot's own builder — no AI key is needed
# just to import this module or render the form.
_builder = None


def _get_builder() -> ProductBuilder:
    global _builder
    if _builder is None:
        _builder = ProductBuilder()
    return _builder


@product_bp.route("/publish_product", methods=["GET"])
def index():
    init_db()
    return render_template("index_products.html")


@product_bp.route("/publish_product", methods=["POST"])
def publish_product():
    """Create a product directly on a chosen tenant's site.

    This used to publish a job onto the `product_jobs` Redis stream for
    workers/product_worker.py to consume — but that worker is retired
    (product creation moved to a synchronous, per-tenant call from the
    bot, see workers/common_handlers.py). This form now does the exact
    same synchronous call so it isn't silently publishing jobs that
    nothing will ever process.
    """
    data = request.json or {}

    tenant_id = data.get("tenant_id")
    title = (data.get("title") or "").strip()
    if not tenant_id:
        return jsonify({"status": "error", "message": "tenant_id لازم است."}), 400
    if not title:
        return jsonify({"status": "error", "message": "عنوان محصول لازم است."}), 400

    connection = get_wp_connection(int(tenant_id))
    if not connection:
        return jsonify({"status": "error", "message": "این تنانت سایتی وصل نکرده است."}), 400

    site = SiteConnectorClient(connection["site_url"], connection["secret"])

    try:
        ai_product = _get_builder().generate_full_product(
            title=title,
            category=data.get("category", ""),
            product_type=data.get("product_type", ""),
            user_notes=data.get("user_notes", ""),
            brand=data.get("brand", ""),
            tags=data.get("tags") or [],
        )
    except Exception as exc:
        log(f"[web publish_product] AI generation failed: {exc}")
        return jsonify({"status": "error", "message": f"سرویس هوش مصنوعی پاسخ نداد: {exc}"}), 502

    payload = {
        "title": title,
        "description": ai_product["description"],
        "slug": ai_product.get("slug"),
        "price": data.get("price", 0),
        "sale_price": data.get("sale_price") or None,
        "category": data.get("category"),
        "brand": ai_product.get("brand") or data.get("brand", "Generic"),
        "tags": [t.strip() for t in ai_product.get("hashtags", "").split(",") if t.strip()],
        "images": data.get("images") or [],
        "meta_title": ai_product["seo"]["title"],
        "meta_description": ai_product["seo"]["description"],
        "keywords": ai_product["seo"]["keywords"],
        "stock_quantity": data.get("stock_quantity", 0),
    }

    try:
        result = site.create_product(payload)
    except SiteConnectorError as exc:
        log(f"[web publish_product] site rejected the product: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 502

    log(f"[web publish_product] created product_id={result.get('product_id')} for tenant={tenant_id}")
    return jsonify({
        "status": "created",
        "product_id": result.get("product_id"),
        "url": result.get("url"),
    })


@product_bp.route("/api/tenants/<int:tenant_id>/categories", methods=["GET"])
def tenant_categories(tenant_id):
    connection = get_wp_connection(tenant_id)
    if not connection:
        return jsonify({"status": "error", "message": "این تنانت سایتی وصل نکرده است."}), 400
    site = SiteConnectorClient(connection["site_url"], connection["secret"])
    try:
        categories = site.get_categories()
    except SiteConnectorError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 502
    return jsonify(categories)