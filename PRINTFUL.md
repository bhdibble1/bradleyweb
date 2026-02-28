# Adding Products to Your Store with the Printful API

Your store keeps products in its own database. You sync **only the products you designed in Printful** (e.g. your mug)—not the full catalog. When customers order, you can later send those orders to Printful for fulfillment (separate step).

## 1. Get a Printful API key

1. Go to [Printful Developer Portal](https://developers.printful.com/) and sign in.
2. Open **Your tokens** and create a **Private Token**.
3. Give it **Store** access and **sync_products/read** (read access to Sync Products). If you plan to create orders in Printful, add **Orders** (read/write).
4. Copy the token and add it to your `.env`:

```env
PRINTFUL_API_KEY=your_private_token_here
```

## 2. Sync only YOUR store products (e.g. your mug)

The script syncs from **Store Products** (the products you added/designed in your Printful dashboard), not the full catalog.

### If you already ran the old sync and have a ton of catalog products

From your project root:

```bash
# Remove all Printful-synced products (clears the catalog junk), then sync only your store products
python -m SS.printful_sync --clear --store
```

### Normal sync (only your designs)

```bash
# Sync your Printful store products only (e.g. your mug)
python -m SS.printful_sync --store
```

Or with no flags (default is to sync store):

```bash
python -m SS.printful_sync
```

### From Flask shell

```bash
flask shell
```

Then:

```python
from SS.printful_sync import clear_printful_products, sync_printful_store_products

# Optional: remove all previously synced Printful products first
clear_printful_products()

# Sync only your store products (your designed mug, etc.)
synced, errors = sync_printful_store_products()
print(f"Synced {synced} products, {len(errors)} errors")
```

## 3. What gets synced

- **Your Printful store products only** (the ones you designed) → your `Product` table:
  - **product_name** = your product name in Printful
  - **product_image** = thumbnail from Printful
  - **price** = first variant’s retail price
  - **quantity** = 99, **category** = "Merch"

Each synced product stores a `printful_id` (e.g. `sync_123`) so the script can update it on later syncs.

## 4. After products are in your store

- They appear on your **Shop** (/products) page like any other product.
- Customers add them to cart and pay with your existing Stripe checkout.
- **Fulfillment:** When you want Printful to print and ship an order, you need to send the order to Printful via their [Orders API](https://developers.printful.com/docs/#tag/Orders-API) (create order, confirm draft). That’s a separate integration (e.g. when an order is paid in your app, call Printful’s “create order” with the items and shipping address).

## 5. Useful Printful API endpoints

| What you want | Endpoint | Notes |
|---------------|----------|--------|
| List catalog products | `GET https://api.printful.com/products` | Use for sync. |
| One product + variants | `GET https://api.printful.com/products/{id}` | Get price/image per variant. |
| Your synced products in Printful | `GET https://api.printful.com/store/products` | Products you added in Printful dashboard; different from catalog. |
| Create order for fulfillment | `POST https://api.printful.com/orders` | Send a paid order to Printful to fulfill. |

All requests need the header: `Authorization: Bearer YOUR_PRINTFUL_API_KEY`.

## 6. Optional: Sync by category

To sync only certain Printful categories (e.g. T‑shirts):

1. Get category IDs: `GET https://api.printful.com/categories`
2. Use the `category_id` query when calling the sync script (see `SS/printful_sync.py` and add a `--category` argument if you need it).
