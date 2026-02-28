"""
One-time script to add the mug product to the store DB.

Run from project root:
  flask add-mug-product

Or with Render DB: set DATABASE_URL to your Render Postgres URL, then run the same command
(locally or in Render Shell).

Image: Set MUG_IMAGE_URL in env, or edit the product in /admin after creation.
"""
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

import os
from SS import create_app
from SS.models import db, Product

MUG_NAME = "MTG Store Mug"
MUG_DESCRIPTION = "Official store mug."
MUG_IMAGE_URL = os.environ.get("MUG_IMAGE_URL", "").strip() or "https://via.placeholder.com/300x300?text=Mug"
MUG_PRICE = 14.99
MUG_QUANTITY = 100
MUG_CATEGORY = "Mugs"


def add_mug_product():
    app = create_app()
    with app.app_context():
        existing = Product.query.filter(Product.product_name == MUG_NAME).first()
        if existing:
            print(f"Product already exists (id={existing.id}). Updating.")
            existing.product_image = MUG_IMAGE_URL
            existing.price = MUG_PRICE
            existing.product_description = MUG_DESCRIPTION
            existing.quantity = MUG_QUANTITY
            existing.category = MUG_CATEGORY
            db.session.commit()
            print("Updated.")
            return existing.id
        p = Product(
            product_name=MUG_NAME,
            product_description=MUG_DESCRIPTION,
            quantity=MUG_QUANTITY,
            product_image=MUG_IMAGE_URL,
            featured=False,
            price=MUG_PRICE,
            category=MUG_CATEGORY,
        )
        db.session.add(p)
        db.session.commit()
        print(f"Created product id={p.id}: {MUG_NAME} @ ${MUG_PRICE}")
        return p.id


if __name__ == "__main__":
    add_mug_product()
