from flask import Blueprint, render_template, redirect, url_for, request, flash, session, jsonify, request
from SS.models import db, User, bcrypt, Product, Order, OrderItem
from SS.forms import RegistrationForm, LoginForm, QuitNicotineGuideForm, PremiumCSRFForm
from SS.emailer import send_email
from flask_login import login_user, current_user, logout_user, login_required
from flask import session
import stripe
import json
import os
import requests
import traceback
from datetime import datetime



main = Blueprint('main', __name__)

PROJECT_SLUGS = {'music': 'Music', 'premed': 'Premed', 'charity': 'Charity', 'vidiography': 'Vidiography', 'chemistry': 'Chemistry'}


@main.route("/projects/<slug>")
def project_page(slug):
    if slug not in PROJECT_SLUGS:
        return redirect(url_for('main.home'))
    return render_template("project_page.html", project_name=PROJECT_SLUGS[slug], slug=slug)


@main.route("/free-quit-nicotine-guide", methods=["GET", "POST"])
def quit_nicotine_guide():
    form = QuitNicotineGuideForm()
    if form.validate_on_submit():
        email = form.email.data.strip()
        download_url = os.environ.get("GUIDE_DOWNLOAD_URL", "").strip()
        from_name = os.environ.get("FROM_NAME", "5 Star Mint")
        if download_url:
            html = f"""
            <p>Thanks for signing up. Here's your free 30-day guide to quit nicotine.</p>
            <p><a href="{download_url}" style="display:inline-block;background:#141414;color:#fff;padding:12px 24px;text-decoration:none;border-radius:8px;">Download the guide</a></p>
            <p>If the button doesn't work, copy this link: {download_url}</p>
            """
        else:
            html = "<p>You're on the list. We'll send your free 30-day quit nicotine guide to this email shortly.</p>"
        sent = send_email(
            to=email,
            subject="Your free 30-day guide to quit nicotine",
            html=html,
            from_name=from_name,
        )
        if sent:
            flash("Check your email for the download link.", "success")
        else:
            flash("We received your email. You'll get the guide soon.", "success")
        return redirect(url_for("main.quit_nicotine_guide"))
    book_image_url = os.environ.get("GUIDE_BOOK_IMAGE_URL", "").strip()
    return render_template("quit_nicotine_guide.html", form=form, book_image_url=book_image_url or None)


EARLY_BIRD_CAPACITY = 10


def _count_active_subscriptions(price_id):
    """Return number of active subscriptions for the given Stripe price ID."""
    if not price_id:
        return None
    try:
        subs = stripe.Subscription.list(price=price_id, status="active", limit=100)
        return len(subs.get("data", []))
    except Exception:
        return None


@main.route("/premium", methods=["GET"])
def premium():
    if request.args.get("success") == "1":
        flash("Thanks for subscribing! Check your email for next steps.", "success")
    price_early = os.environ.get("STRIPE_PRICE_EARLY_BIRD_GOLD", "").strip()
    count = _count_active_subscriptions(price_early) if price_early else None
    early_bird_spots_left = (EARLY_BIRD_CAPACITY - count) if count is not None else None
    regular_price = os.environ.get("PREMIUM_REGULAR_MEMBER_PRICE", "5")
    form = PremiumCSRFForm()
    return render_template(
        "premium.html",
        form=form,
        early_bird_spots_left=early_bird_spots_left,
        regular_member_price=regular_price,
    )


VALID_TIERS = ("early_bird_gold", "regular", "gold")


@main.route("/create-membership-checkout-session", methods=["POST"])
def create_membership_checkout_session():
    tier = (request.form.get("tier") or "").strip()
    if tier not in VALID_TIERS:
        flash("Invalid membership tier.", "danger")
        return redirect(url_for("main.premium"))
    price_ids = {
        "early_bird_gold": os.environ.get("STRIPE_PRICE_EARLY_BIRD_GOLD", "").strip(),
        "regular": os.environ.get("STRIPE_PRICE_REGULAR_MEMBER", "").strip(),
        "gold": os.environ.get("STRIPE_PRICE_GOLD", "").strip(),
    }
    price_id = price_ids.get(tier)
    if not price_id:
        flash("This membership is not set up yet. Add your Stripe price IDs to the server (.env) and try again.", "warning")
        return redirect(url_for("main.premium"))
    if tier == "early_bird_gold":
        count = _count_active_subscriptions(price_id)
        if count is not None and count >= EARLY_BIRD_CAPACITY:
            flash("Early Bird Gold is sold out (10 spots filled).", "warning")
            return redirect(url_for("main.premium"))
    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=url_for("main.premium", _external=True) + "?success=1",
            cancel_url=url_for("main.premium", _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except stripe.error.StripeError as e:
        flash(f"Could not start checkout: {str(e)}", "danger")
        return redirect(url_for("main.premium"))


# utils/cart.py or just at the top of routes.py if small project
@main.route('/cart/json')
def get_cart_json():
    return jsonify(get_cart())

def get_cart_total():
    cart = get_cart()
    total_items = 0

    for product_id_str, quantity in cart.items():
        product = Product.query.get(int(product_id_str))
        if product and product.category != 'Promo':
            total_items += quantity

    return total_items


def check_free_booster_pack():
    cart = get_cart()  # Get the cart from the session

    # Check if there is any sealed product in the cart
    has_sealed = any(
        product and product.category == 'Sealed' 
        for product_id, quantity in cart.items() 
        for product in [Product.query.get(product_id)]
    )

    # If there are sealed products, make sure free booster is in cart
    if has_sealed:
        # Find the Free Booster Pack product
        free_booster = Product.query.filter(Product.product_name.ilike('Free Booster Pack')).first()
        if free_booster:
            free_booster_id = str(free_booster.id)
            if free_booster_id not in cart:
                cart[free_booster_id] = 1  # Add one booster pack
                save_cart(cart)
                flash('Free Booster Pack added to cart!', 'success')

    # If no sealed products, remove free booster if present
    else:
        for product_id in list(cart.keys()):
            product = Product.query.get(product_id)
            if product and product.product_name.lower() == 'free booster pack':
                cart.pop(product_id)
                save_cart(cart)
                flash('Free Booster Pack removed (no sealed products in cart).', 'warning')
                break

# Keep the rest of your functions as is
def get_cart():
    return session.get('cart', {})

def save_cart(cart):
    session['cart'] = cart

def add_to_cart(product_id, quantity=1):
    cart = get_cart()

    # Safely add/update quantity
    product_id = str(product_id)  # always string for consistency
    cart[product_id] = cart.get(product_id, 0) + quantity

    save_cart(cart)

def update_cart(product_id, quantity):
    cart = get_cart()
    product_id = str(product_id)

    if quantity <= 0:
        cart.pop(product_id, None)  # Remove if quantity is 0 or less
    else:
        cart[product_id] = quantity

    save_cart(cart)

def clear_cart():
    session.pop('cart', None)




def remove_promo_if_no_sealed(cart):
    """
    Removes Free Booster Pack if no sealed products are left in the cart.
    Assumes 'sealed' products have category exactly 'sealed'.
    """
    has_sealed = False

    # First: Check if there are any sealed products
    for product_id in cart.keys():
        product = Product.query.get(int(product_id))  # cast to int if necessary
        if product and product.category and product.category.lower() == 'sealed':
            has_sealed = True
            break

    # Second: If no sealed, remove booster pack
    if not has_sealed:
        for product_id in list(cart.keys()):
            product = Product.query.get(int(product_id))
            if product and product.product_name and product.product_name.lower() == 'free booster pack':
                cart.pop(product_id)
                save_cart(cart)
                flash('Free Booster Pack removed (no sealed products in cart).', 'warning')
                break


@main.route('/')
@main.route('/home')
def home():
    return render_template('channel_home.html')


@main.route('/shop')
def shop():
    """Store landing page (products, promos)."""
    return render_template('home.html')

@main.route('/orders')
@login_required  # Ensure the user is logged in
def orders():
    # Fetch orders for the logged-in user
    user_orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('orders.html', user=current_user, orders=user_orders)

@main.route("/products")
def products():
    try:
        category = request.args.get('category')  # Get 'category' from query string (e.g., /products?category=electronics)

        if category:
            # Filter by category if specified
            products = Product.query.filter(Product.category == category).all()
        else:
            # Otherwise, show all products
            products = Product.query.all()

        return render_template('products.html', products=products)
    except Exception as e:
        traceback.print_exc()
        raise



@main.route('/cart')
def cart():
    cart = session.get('cart', {})
    products = Product.query.filter(Product.id.in_(cart.keys())).all()
    remove_promo_if_no_sealed(cart)
    check_free_booster_pack()
    cart_items = []
    total = 0
    for product in products:
        quantity = cart[str(product.id)]
        subtotal = product.price * quantity
        cart_items.append({
            'product': product,
            'quantity': quantity,
            'subtotal': subtotal
        })
        total += subtotal

    return render_template('cart.html', cart_items=cart_items, total=total)

@main.route('/account')
@login_required
def account():
    return render_template('account.html')

@main.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', {})

    cart_items = []
    total_items = 0
    cart_total_price = 0

    for product_id, quantity in cart.items():
        product = Product.query.get(product_id)
        item_total = product.price * quantity
        cart_items.append({
            'id': product.id,
            'name': product.product_name,
            'price': product.price,
            'quantity': quantity,
            'image': product.product_image,
        })
        total_items += quantity
        cart_total_price += item_total

        remove_promo_if_no_sealed(cart)
        check_free_booster_pack()

    return render_template('checkout.html', cart_items=cart_items, total_items=total_items, cart_total_price=cart_total_price)


@main.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('main.home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@main.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = RegistrationForm()

    # Check if form is valid and submitted
    if form.validate_on_submit():
        # Check if email already exists in the database
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash('That email is already registered. Please log in or use a different email.', 'danger')
            return redirect(url_for('main.register'))

        # Hash the password
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')

        # Create new user and add to the database
        user = User(email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('main.login'))

    return render_template('register.html', title='Register', form=form)


@main.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main.home'))

@main.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    cart = session.get('cart', {})

    if not cart:
        flash('Your cart is empty. Please add items before proceeding to checkout.', 'warning')
        return redirect(url_for('main.cart'))

    user_id = current_user.id if current_user.is_authenticated else None

    line_items = []
    for product_id, quantity in cart.items():
        product = Product.query.get(product_id)
        if not product:
            continue

        line_items.append({
            'price_data': {
                'currency': 'usd',
                'unit_amount': int(product.price * 100),
                'product_data': {
                    'name': product.product_name,
                },
            },
            'quantity': quantity,
        })

    # Create Stripe checkout session
    session_data = stripe.checkout.Session.create(
        metadata={
            'user_id': str(user_id) if user_id else '',
            'cart': json.dumps(cart)
        },
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=url_for('main.payment_success', _external=True),
        cancel_url=url_for('main.cart', _external=True),
        shipping_address_collection={'allowed_countries': ['US', 'CA']},
        shipping_options=[{
            'shipping_rate_data': {
                'type': 'fixed_amount',
                'fixed_amount': {
                    'amount': 500,
                    'currency': 'usd',
                },
                'display_name': 'Standard shipping',
                'delivery_estimate': {
                    'minimum': {'unit': 'business_day', 'value': 5},
                    'maximum': {'unit': 'business_day', 'value': 7},
                },
            }
        }]
    )

    session.pop('cart', None)

    return redirect(session_data.url, code=303)


@main.route('/create-bitcoin-checkout-session', methods=['POST'])
def create_bitcoin_checkout_session():
    cart = session.get('cart', {})

    if not cart:
        flash('Your cart is empty. Please add items before proceeding to checkout.', 'warning')
        return redirect(url_for('main.cart'))

    # Calculate total price
    cart_total_price = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(product_id)
        if not product:
            continue
        cart_total_price += product.price * quantity

    # BTCPay Server Info
    BTCPAY_API_KEY = 'your-btcpay-api-key'
    BTCPAY_STORE_ID = 'your-store-id'
    BTCPAY_URL = 'https://your-btcpay-server.com'

    headers = {
        'Authorization': f'Token {BTCPAY_API_KEY}',
        'Content-Type': 'application/json'
    }

    payload = {
        "amount": str(cart_total_price),
        "currency": "USD",
        "checkout": {
            "speedPolicy": "HighSpeed",
            "paymentMethods": ["BTC"],
            "redirectURL": url_for('main.payment_success', _external=True),
            "defaultLanguage": "en"
        },
        "metadata": {
            "user_id": str(current_user.id) if current_user.is_authenticated else '',
            "cart": json.dumps(cart)
        }
    }

    response = requests.post(
        f'{BTCPAY_URL}/api/v1/stores/{BTCPAY_STORE_ID}/invoices',
        headers=headers,
        json=payload
    )

    if response.status_code == 200:
        invoice = response.json()
        session.pop('cart', None)
        return redirect(invoice['checkoutLink'])
    else:
        flash('Failed to create Bitcoin payment session. Please try again.', 'danger')
        return redirect(url_for('main.cart'))

@main.route("/tasks/send-order-email", methods=["POST"])
def task_send_order_email():
    token = request.headers.get("X-Task-Token", "")
    expected = os.environ.get("TASK_TOKEN", "")
    if not expected or token != expected:
        print("❌ email task unauthorized (bad/missing X-Task-Token)")
        return "unauthorized", 401

    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    email = data.get("email")
    print(f"📬 email task received order_id={order_id}, email={email}")

    if not order_id:
        return "missing order_id", 400

    from SS.models import db, Order, OrderItem, Product, User
    order = Order.query.get(order_id)
    if not order:
        print("❌ order not found")
        return "order not found", 404

    if not email and getattr(order, "user_id", None):
        u = User.query.get(order.user_id)
        email = getattr(u, "email", None)

    if not email:
        print("ℹ️ no recipient email available; skipping send")
        return "no recipient email", 200

    items = OrderItem.query.filter_by(order_id=order.id).all()
    lis = []
    for oi in items:
        p = Product.query.get(oi.product_id)
        name = p.product_name if p else f"Product {oi.product_id}"
        lis.append(f"<li>{oi.quantity} × {name} — ${float(oi.subtotal):.2f}</li>")

    html = f"""
    <h2>Thanks for your order!</h2>
    <p>Order ID: <strong>{order.id}</strong></p>
    <ul>{''.join(lis)}</ul>
    <p>Total: <strong>${float(order.total):.2f}</strong></p>
    """

    from SS.emailer import send_email
    ok = send_email(to=email, subject=f"Order #{order.id} confirmation", html=html)
    print(f"📧 send_email returned: {ok}")

    if ok and hasattr(order, "confirmation_sent"):
        order.confirmation_sent = True
        db.session.commit()

    return ("sent", 200) if ok else ("send failed", 200)


@main.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    import os, json, stripe, traceback, requests
    from datetime import datetime
    from sqlalchemy.exc import SQLAlchemyError
    from SS.models import db, Product, Order, OrderItem

    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError:
        return "bad signature", 400
    except Exception:
        return "invalid payload", 400

    etype = event.get("type")

    def set_if_attr(obj, name, value):
        if hasattr(obj, name):
            setattr(obj, name, value)

    def upsert_order_and_reduce_stock(meta, session_id=None, pi_id=None):
        # cart from metadata (JSON string)
        raw_cart = (meta or {}).get("cart", "{}")
        try:
            cart = json.loads(raw_cart) if isinstance(raw_cart, str) else (raw_cart or {})
        except Exception:
            cart = {}

        # optional user_id from metadata
        user_id = (meta or {}).get("user_id")
        if isinstance(user_id, str) and user_id.isdigit():
            user_id = int(user_id)
        else:
            user_id = None

        # try to find an existing order (idempotency)
        order = None
        try:
            if session_id and hasattr(Order, "stripe_session_id"):
                order = Order.query.filter_by(stripe_session_id=session_id).first()
            if not order and pi_id and hasattr(Order, "payment_intent_id"):
                order = Order.query.filter_by(payment_intent_id=pi_id).first()
        except Exception:
            pass

        if not order:
            order = Order(order_date=datetime.utcnow(), total=0.0)
            if user_id and hasattr(order, "user_id"):
                order.user_id = user_id
            set_if_attr(order, "stripe_session_id", session_id)
            set_if_attr(order, "payment_intent_id", pi_id)
            set_if_attr(order, "status", "paid")
            set_if_attr(order, "paid_at", datetime.utcnow())
            set_if_attr(order, "inventory_reduced", False)
            set_if_attr(order, "confirmation_sent", False)
            db.session.add(order)
            db.session.flush()  # ensure order.id

        existing = {oi.product_id: oi for oi in OrderItem.query.filter_by(order_id=order.id).all()}
        total = 0.0

        for pid_str, qty in (cart or {}).items():
            try:
                pid = int(pid_str); qty = int(qty)
            except Exception:
                continue

            product = Product.query.get(pid)
            if not product:
                continue

            already = existing.get(pid).quantity if pid in existing else 0
            delta = max(0, qty - already)

            line_total = float(product.price) * qty
            total += line_total

            if pid in existing:
                item = existing[pid]
                item.quantity = qty
                item.subtotal = line_total
            else:
                if qty > 0:
                    db.session.add(OrderItem(
                        order_id=order.id,
                        product_id=pid,
                        quantity=qty,
                        subtotal=line_total
                    ))

            if delta > 0 and product.quantity is not None:
                if delta > product.quantity:
                    delta = product.quantity
                product.quantity -= delta

        order.total = total
        set_if_attr(order, "status", "paid")
        set_if_attr(order, "inventory_reduced", True)
        db.session.commit()
        return order.id  # return id we just updated/created

    try:
        if etype == "checkout.session.completed":
            s = event["data"]["object"]
            if s.get("payment_status") == "paid":
                order_id = upsert_order_and_reduce_stock(
                    meta=s.get("metadata") or {},
                    session_id=s.get("id"),
                    pi_id=s.get("payment_intent"),
                )
                # pass customer email to the task (best available source)
                customer_email = (s.get("customer_details") or {}).get("email") or s.get("customer_email")
                task_token = os.environ.get("TASK_TOKEN", "")
                if order_id and task_token:
                    try:
                        print(f"→ queue email task for order {order_id} to {customer_email}")
                        requests.post(
                            url_for('main.task_send_order_email', _external=True),
                            json={"order_id": order_id, "email": customer_email},
                            headers={"X-Task-Token": task_token},
                            timeout=2,
                        )
                    except Exception as e:
                        print("⚠️ email task post failed:", e)
                else:
                    if not task_token:
                        print("⚠️ TASK_TOKEN not set; skipping email task.")
                return "ok", 200
            return "ignored (not paid)", 200

        if etype == "payment_intent.succeeded":
            # we’ll still reduce inventory here (idempotent) but skip email
            pi = event["data"]["object"]
            upsert_order_and_reduce_stock(meta=pi.get("metadata") or {}, pi_id=pi.get("id"))
            return "ok", 200

    except SQLAlchemyError:
        db.session.rollback()
        traceback.print_exc()
        return "db error", 500
    except Exception:
        db.session.rollback()
        traceback.print_exc()
        return "error", 500

    return "ignored", 200


@main.route('/payment-success')
def payment_success():
    return render_template('payment_success.html')  # Make sure you have this template

def remove_from_cart(product_id):
    cart = session.get('cart', {})
    if product_id in cart:
        del cart[product_id]
        save_cart(cart)  # Save cart after removal

    # After removing, check if Free Booster Pack should still be there
    cart = session.get('cart', {})
    remove_promo_if_no_sealed(cart)
    check_free_booster_pack()

    save_cart(cart)  # Ensure the cart is saved after promo checks
    return redirect(url_for('main.cart'))  # Only one redirect is necessary

@main.route('/store', methods=['GET'])
def store():
    return render_template('store.html')

@main.route('/store/card-search', methods=['GET'])
def store_card_search():
    card_name = request.args.get('card_name', '').strip()  # Ensure trimming spaces
    if not card_name:
        return jsonify({'error': 'Card name is required.'})  # Return error if no card name provided

    # Call Scryfall API
    url = f'https://api.scryfall.com/cards/search?q={card_name}'
    response = requests.get(url)

    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch from Scryfall'})

    data = response.json()
    results = []
    for card in data.get('data', [])[:5]:  # Limit to top 5 results
        card_info = {
            'name': card.get('name'),
            'image': card.get('image_uris', {}).get('normal', '') if card.get('image_uris') else '',
            'price': card.get('prices', {}).get('usd', 'N/A')
            
        }

        # Check if the product exists in the database
        product = Product.query.filter_by(product_name=card_info['name']).first()

        # Check if the product exists in the database
        if product:
            # Override with database price and quantity
            card_info['price'] = product.price
            card_info['quantity'] = product.quantity
            card_info['out_of_stock'] = product.quantity == 0
            card_info['id'] = product.id  # Add product ID here
        else:
            # If the product is not found, set the quantity to 0 and mark as out of stock
            card_info['price'] = 'NA'  # Or whatever default price you'd like to set
            card_info['quantity_in_stock'] = 0
            card_info['out_of_stock'] = True


        results.append(card_info)

    return jsonify(results)

@main.route('/add_to_cart', methods=['POST'])
def add_to_cart_route():
    try:
        # Retrieve and validate product ID and quantity
        product_id_raw = request.form.get('product_id')
        quantity_raw = request.form.get('quantity', 1)

        print(f"Form data: product_id={product_id_raw}, quantity={quantity_raw}")

        try:
            product_id = int(product_id_raw)
            quantity = int(quantity_raw)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid product ID or quantity format'}), 400

        if quantity < 1:
            return jsonify({'success': False, 'error': 'Quantity must be at least 1'}), 400

        # Fetch product from database
        product = Product.query.get(product_id)
        if not product:
            print(f"Product not found: {product_id}")
            return jsonify({'success': False, 'error': 'Product not found'}), 404

        # Get existing quantity in cart (if any)
        cart = get_cart()
        current_cart_qty = cart.get(str(product_id), 0)
        total_requested = current_cart_qty + quantity

        # Check against available stock
        if total_requested > product.quantity:
            print(f"Insufficient stock for product {product_id}. Requested total: {total_requested}, Available: {product.quantity}")
            return jsonify({'success': False, 'error': 'Not enough stock for this quantity'}), 400

        # Add to cart and handle promo
        add_to_cart(product.id, quantity)
        check_free_booster_pack()

        cart_total = get_cart_total()

        flash('Item added to cart!', 'success')
        return jsonify({'success': True, 'message': 'Item added to cart!', 'cart_total': cart_total}), 200

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({'success': False, 'error': 'Server error: ' + str(e)}), 500


@main.route('/update_cart', methods=['POST'])
def update_cart():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))

    if quantity <= 0:
        remove_from_cart(product_id)
        flash('Item removed from cart.', 'info')
    else:
        cart = get_cart()
        cart[str(product_id)] = quantity
        save_cart(cart)
        flash('Cart updated successfully!', 'success')

    # No matter what happened (remove or update), always:
    check_free_booster_pack()  # Re-check if free booster needs to be added or removed

    return redirect(url_for('main.cart'))

