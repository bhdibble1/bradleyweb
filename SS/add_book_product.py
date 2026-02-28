"""
One-time script to add the book preorder product.

Run from project root (no pasting needed):
  flask add-book-product

Image: Cloudinary asset from your console link. If the image doesn't show on the store,
get the delivery URL in Cloudinary (Media Library → image → Copy URL) and edit the
product in /admin to paste the correct image URL.
"""
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from SS import create_app
from SS.models import db, Product

# Your Cloudinary cloud name (from your headshot URL). Asset ID from console link.
CLOUDINARY_CLOUD = "dzt95pn0s"
CLOUDINARY_ASSET_ID = "fb8bb2cb30cc20e77cc9691b9a72d506"
# Delivery URL (if 404, replace in Flask-Admin after run)
BOOK_IMAGE_URL = f"https://res.cloudinary.com/{CLOUDINARY_CLOUD}/image/upload/{CLOUDINARY_ASSET_ID}"

BOOK_NAME = "The Wayside: Stories of Those Left Behind (Preorder)"
BOOK_DESCRIPTION = "Preorder — stories of those left behind. Ships when released."
# Self-pub paperback: printing often $2–5/copy; $18.99 gives healthy margin and is a standard preorder price.
BOOK_PRICE = 18.99
BOOK_QUANTITY = 500
BOOK_CATEGORY = "Books"


def add_book_product():
    app = create_app()
    with app.app_context():
        existing = Product.query.filter(Product.product_name == BOOK_NAME).first()
        if existing:
            print(f"Product already exists (id={existing.id}). Updating image and price.")
            existing.product_image = BOOK_IMAGE_URL
            existing.price = BOOK_PRICE
            existing.product_description = BOOK_DESCRIPTION
            existing.quantity = BOOK_QUANTITY
            existing.category = BOOK_CATEGORY
            db.session.commit()
            print("Updated.")
            return existing.id
        p = Product(
            product_name=BOOK_NAME,
            product_description=BOOK_DESCRIPTION,
            quantity=BOOK_QUANTITY,
            product_image=BOOK_IMAGE_URL,
            featured=False,
            price=BOOK_PRICE,
            category=BOOK_CATEGORY,
        )
        db.session.add(p)
        db.session.commit()
        print(f"Created product id={p.id}: {BOOK_NAME} @ ${BOOK_PRICE}")
        return p.id


if __name__ == "__main__":
    add_book_product()
