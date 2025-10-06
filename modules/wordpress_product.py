from clients.woocommerce_client import WooCommerceClient

class WordPressProductModule:
    def __init__(self):
        self.wp = WooCommerceClient()

    def create_product(
        self, title, description, price=0, sale_price=None, category=None, brand=None,
        tags=None, images=None, meta_title=None, meta_description=None, keywords=None, status="publish"
    ):
        # --- category ---
        categories = []
        if category:
            try:
                cat_id = self.wp.get_or_create_category(category)
                categories.append({"id": cat_id})
            except Exception as e:
                print(f"⚠️ Category error: {e}")

        # --- tags ---
        tags_data = []
        if tags:
            for t in tags:
                if not t.strip():
                    continue
                try:
                    tag_id = self.wp.get_or_create_tag(t.strip())
                    tags_data.append({"id": tag_id})
                except Exception as e:
                    print(f"⚠️ Tag error: {e}")

        # --- general data ---
        data = {
            "name": title,
            "type": "simple",
            "regular_price": str(price),
            "description": description,
            "short_description": description[:200],
            "categories": categories,
            "tags": tags_data,
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

        # --- picture (link or None) ---
        if images:
            # if link
            valid_images = [img for img in images if img.startswith("http")]
            if valid_images:
                data["images"] = [{"src": img} for img in valid_images]

        product = self.wp.create_product(data)
        return product.get("id")

    def upload_media(self, product_id, image_bytes, filename="image.jpg"):
        return self.wp.upload_product_media(product_id, image_bytes, filename)
