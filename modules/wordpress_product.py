import os
# import time

from typing import List, Union, Optional

from clients.woocommerce_client import WooCommerceClient

class WordPressProductModule:
    def __init__(self):
        self.wp = WooCommerceClient()

    def create_product(
        self,
        title: str,
        description: str,
        price: float = 0,
        sale_price: Optional[float] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        tags: Optional[List[str]] = None,
        images: Optional[List[str]] = None,  # list of URLs or local file paths
        meta_title: Optional[str] = None,
        meta_description: Optional[str] = None,
        keywords: Optional[str] = None,
        color: Optional[str] = None,
        stock_quantity: Optional[Union[int, str]] = None,
        status: str = "publish",
        upload_images: bool = True
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
                t = t.strip()
                if not t:
                    continue
                try:
                    tag_id = self.wp.get_or_create_tag(t)
                    tags_data.append({"id": tag_id})
                except Exception as e:
                    print(f"⚠️ Tag error: {e}")

        # --- attributes (color) ---
        attributes = []
        if color:
            # WooCommerce attribute structure (for simple custom attribute)
            attributes.append({
                "name": "Color",
                "options": [color],
                "visible": True,
                "variation": False
            })

        # --- meta_data ---
        meta_data = []
        if brand:
            meta_data.append({"key": "brand", "value": brand})
        if meta_title:
            meta_data.append({"key": "_yoast_wpseo_title", "value": meta_title})
        if meta_description:
            meta_data.append({"key": "_yoast_wpseo_metadesc", "value": meta_description})
        if keywords:
            meta_data.append({"key": "_yoast_wpseo_focuskw", "value": keywords})
        if color:
            meta_data.append({"key": "color", "value": color})

        # --- stock handling ---
        manage_stock = False
        stock_qty = None
        stock_status = "instock"
        if stock_quantity is not None and stock_quantity != "":
            try:
                stock_qty = int(stock_quantity)
                manage_stock = True
                stock_status = "instock" if stock_qty > 0 else "outofstock"
                # fallback: ignore invalid stock value
            except (ValueError, TypeError):
                stock_qty = None
                manage_stock = False

        # --- initial product payload (without images) ---
        data = {
            "name": title,
            "type": "simple",
            "regular_price": str(price),
            "description": description,
            "short_description": (description or "")[:200],
            "categories": categories,
            "tags": tags_data,
            "meta_data": meta_data,
            "attributes": attributes,
            "status": status,
            # stock fields:
            "manage_stock": manage_stock,
        }

        if sale_price:
            data["sale_price"] = str(sale_price)
        if manage_stock and stock_qty is not None:
            data["stock_quantity"] = stock_qty
            data["stock_status"] = stock_status
        else:
            # If the user hasn't entered anything, WooCommerce will set the status itself
            data["stock_status"] = "instock"
            
        # 1) Create product first (without images)
        product = self.wp.create_product(data)
        product_id = product.get("id") if isinstance(product, dict) else None

        if not product_id:
            raise Exception("❌ Failed to create product in WordPress.")

        # 2) Handle images:
        # prepare images_payload as list of {"src": url} or {"id": media_id}
        # --- inside create_product ---
        images_payload = []
        if images:
            for i, img in enumerate(images):
                if not img:
                    continue
                img = img.strip()

                if img.startswith("http://") or img.startswith("https://"):
                    # ✅ Just attach, don't re-upload
                    images_payload.append({"src": img, "position": i})
                else:
                    # If you have a local path and upload_images = True
                    if upload_images:
                        try:
                            abs_path = os.path.abspath(img)
                            with open(abs_path, "rb") as f:
                                image_bytes = f.read()
                            media_id = self.wp.upload_product_media(
                                product_id,
                                image_bytes,
                                filename=os.path.basename(abs_path)
                            )
                            if media_id:
                                images_payload.append({"id": media_id, "position": i})
                        except Exception as e:
                            print(f"⚠️ Image upload error for {img}: {e}")

        # Attach images to the product (only once)
        if images_payload:
            try:
                updated = self.wp.update_product(product_id, {"images": images_payload})
                return updated
            except Exception as e:
                print(f"⚠️ Failed to attach images to product {product_id}: {e}")
                return product # fallback: return the created product as-is

        # else: no images provided — fine.
        return product  # ✅ just return created product if no images

    def upload_media(self, product_id, image_bytes, filename="image.jpg"):
        return self.wp.upload_product_media(product_id, image_bytes, filename)
