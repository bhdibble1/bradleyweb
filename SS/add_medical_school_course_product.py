"""
One-time script to add the Medical School course product ($97) to the store DB.

Run from project root:
  python SS/add_medical_school_course_product.py

Or with app context:
  flask shell
  >>> from SS.add_medical_school_course_product import add_medical_school_course_product
  >>> add_medical_school_course_product()

After creation, set MEDICAL_SCHOOL_COURSE_PRODUCT_ID in your environment to the
printed product id so one-time purchasers get access to the course.
"""
from pathlib import Path
import sys

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(_project_root / ".env")
except Exception:
    pass

import os
from SS import create_app
from SS.models import db, Product

COURSE_NAME = "Getting into Medical School (Course)"
COURSE_DESCRIPTION = "One-time purchase: full access to the Getting into Medical School course."
COURSE_IMAGE_URL = os.environ.get("MEDICAL_SCHOOL_COURSE_IMAGE_URL", "").strip() or "https://via.placeholder.com/300x300?text=Course"
COURSE_PRICE = 97.00
COURSE_QUANTITY = 9999
COURSE_CATEGORY = "Course"


def add_medical_school_course_product():
    app = create_app()
    with app.app_context():
        existing = Product.query.filter(Product.product_name == COURSE_NAME).first()
        if existing:
            print(f"Product already exists (id={existing.id}). Updating.")
            existing.product_image = COURSE_IMAGE_URL
            existing.price = COURSE_PRICE
            existing.product_description = COURSE_DESCRIPTION
            existing.quantity = COURSE_QUANTITY
            existing.category = COURSE_CATEGORY
            db.session.commit()
            print("Updated. Set MEDICAL_SCHOOL_COURSE_PRODUCT_ID={}".format(existing.id))
            return existing.id
        p = Product(
            product_name=COURSE_NAME,
            product_description=COURSE_DESCRIPTION,
            quantity=COURSE_QUANTITY,
            product_image=COURSE_IMAGE_URL,
            featured=False,
            price=COURSE_PRICE,
            category=COURSE_CATEGORY,
        )
        db.session.add(p)
        db.session.commit()
        print("Created product id={}: {} @ ${}".format(p.id, COURSE_NAME, COURSE_PRICE))
        print("Set MEDICAL_SCHOOL_COURSE_PRODUCT_ID={} in your environment.".format(p.id))
        return p.id


if __name__ == "__main__":
    add_medical_school_course_product()
