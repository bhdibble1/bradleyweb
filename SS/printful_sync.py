"""
Sync Printful STORE products (products you designed in Printful) into the store's Product table.
Does NOT sync the full catalog—only your store products (e.g. your mug).
Requires PRINTFUL_API_KEY in environment.

Usage:
  # Remove all previously synced Printful products (catalog or store), then sync only your store products (e.g. mug):
  python -m SS.printful_sync --clear --store

  # Sync only your store products (no clear):
  python -m SS.printful_sync --store

  # Clear only (removes all products that have printful_id set):
  python -m SS.printful_sync --clear

  flask shell:
  from SS.printful_sync import clear_printful_products, sync_printful_store_products
  clear_printful_products()   # remove catalog junk
  sync_printful_store_products()  # sync only your designed products
"""
import os
import requests
from SS.models import db, Product
from SS import create_app


PRINTFUL_BASE = "https://api.printful.com"


def _headers():
    key = os.environ.get("PRINTFUL_API_KEY", "").strip()
    if not key:
        raise ValueError("PRINTFUL_API_KEY is not set in environment")
    return {"Authorization": f"Bearer {key}"}


def clear_printful_products():
    """Remove all products that were synced from Printful (catalog or store)."""
    app = create_app()
    with app.app_context():
        deleted = Product.query.filter(Product.printful_id.isnot(None)).delete()
        db.session.commit()
        return deleted


def _get_store_products_list():
    """GET /store/products - list of your sync products (the ones you designed)."""
    url = f"{PRINTFUL_BASE}/store/products"
    r = requests.get(url, headers=_headers(), params={"limit": 100}, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("result", []) if isinstance(data, dict) else []


def _get_store_product_detail(sync_product_id):
    """GET /store/products/{id} - one sync product with variants (price, image)."""
    url = f"{PRINTFUL_BASE}/store/products/{sync_product_id}"
    r = requests.get(url, headers=_headers(), timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("result") if isinstance(data, dict) else None


def sync_printful_store_products():
    """
    Sync only YOUR Printful store products (the ones you designed, e.g. your mug)
    into the local Product table. Does not touch the full catalog.
    Returns (synced_count, list_of_errors).
    """
    app = create_app()
    with app.app_context():
        store_list = _get_store_products_list()
        synced = 0
        errors = []
        for item in store_list:
            sync_id = item.get("id")
            if sync_id is None:
                continue
            try:
                detail = _get_store_product_detail(sync_id)
                if not detail:
                    continue
                sync_product = detail.get("sync_product") or {}
                sync_variants = detail.get("sync_variants") or []
                name = (sync_product.get("name") or item.get("name") or "Printful Item")[:100]
                thumbnail = sync_product.get("thumbnail_url") or item.get("thumbnail_url") or ""
                price = 0.0
                for v in sync_variants[:1]:
                    rp = v.get("retail_price")
                    if rp is not None:
                        try:
                            price = float(rp)
                            break
                        except (TypeError, ValueError):
                            pass
                if not thumbnail and sync_variants:
                    prod = sync_variants[0].get("product") or {}
                    thumbnail = prod.get("image") or thumbnail
                if not thumbnail:
                    thumbnail = "https://via.placeholder.com/300?text=Printful"
                printful_id = f"sync_{sync_id}"
                data = {
                    "printful_id": printful_id,
                    "product_name": name,
                    "product_description": (sync_product.get("name") or "Your design")[:100],
                    "product_image": thumbnail,
                    "quantity": 99,
                    "price": price,
                    "category": "Merch",
                }
                existing = Product.query.filter_by(printful_id=printful_id).first()
                if existing:
                    existing.product_name = data["product_name"]
                    existing.product_description = data["product_description"]
                    existing.product_image = data["product_image"]
                    existing.quantity = data["quantity"]
                    existing.price = data["price"]
                    existing.category = data["category"]
                    db.session.commit()
                    synced += 1
                else:
                    db.session.add(Product(**data))
                    db.session.commit()
                    synced += 1
            except Exception as e:
                errors.append((sync_id, str(e)))
        return synced, errors


if __name__ == "__main__":
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    import argparse
    parser = argparse.ArgumentParser(description="Printful: sync only YOUR store products (e.g. mug), not full catalog")
    parser.add_argument("--clear", action="store_true", help="Remove all Printful-synced products first (cleans catalog junk)")
    parser.add_argument("--store", action="store_true", help="Sync your Printful store products (default: True if no other action)")
    args = parser.parse_args()
    do_store = args.store or (not args.clear and not args.store)  # sync store by default; --clear only = no sync
    if args.clear:
        n = clear_printful_products()
        print(f"Cleared {n} Printful-synced products.")
    if do_store or args.store:
        try:
            synced, errs = sync_printful_store_products()
            print(f"Synced {synced} store product(s) (your designs only).")
            if errs:
                print("Errors:", errs)
        except Exception as e:
            print("Error:", e)
            raise
