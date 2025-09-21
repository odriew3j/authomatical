from clients.woocommerce_client import WooCommerceClient

class WordPressProductModule:
    def __init__(self):
        self.wp = WooCommerceClient()

    def create_product(
        self, title, description, price=0, sale_price=None, category=None, brand=None,
        tags=None, images=None, meta_title=None, meta_description=None, keywords=None, status="publish"
    ):
        data = {
            "name": title,
            "type": "simple",
            "regular_price": str(price),
            "description": description,
            "short_description": description[:200],
            "categories": [{"name": category}] if category else [],
            "tags": [{"name": t.strip()} for t in tags] if tags else [],
            "meta_data": [],
            "status": status
        }

        if sale_price:
            data["sale_price"] = str(sale_price)
        if brand:
            data["meta_data"].append({"key": "brand", "value": brand})
        if meta_title:
            data["meta_data"].append({"key": "_yoast_wpseo_title", "value": meta_title})
        if meta_description:
            data["meta_data"].append({"key": "_yoast_wpseo_metadesc", "value": meta_description})
        if keywords:
            data["meta_data"].append({"key": "_yoast_wpseo_focuskw", "value": keywords})
        if images:
            data["images"] = [{"src": img} for img in images]

        product = self.wp.create_product(data)
        return product.get("id")

    def upload_media(self, product_id, image_bytes, filename="image.jpg"):
        return self.wp.upload_product_media(product_id, image_bytes, filename)
