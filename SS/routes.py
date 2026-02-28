from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, jsonify, current_app
from sqlalchemy import func, or_
from SS.models import db, User, bcrypt, Product, Order, OrderItem, Membership
from SS.forms import RegistrationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm, QuitNicotineGuideForm, PremiumCSRFForm
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


def membership_required(*allowed_tiers):
    """
    Decorator: require an active membership. If allowed_tiers is given, the membership's tier must be one of them.
    Use after @login_required.

    Examples:
        @membership_required()                    # any active membership
        @membership_required("gold", "early_bird_gold")  # only gold or early_bird_gold
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("main.login", next=request.url))
            membership = _get_user_membership(current_user.id)
            if not membership:
                flash("This page is for premium members. Subscribe to get access.", "warning")
                return redirect(url_for("main.premium"))
            if allowed_tiers and membership.tier not in allowed_tiers:
                flash("This page requires a different membership tier. Upgrade or change plan to get access.", "warning")
                return redirect(url_for("main.premium"))
            return f(*args, **kwargs)
        return wrapped
    return decorator

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

# Env keys: Stripe Product IDs (prod_xxx) for each membership tier
PREMIUM_PRODUCT_KEYS = {
    "early_bird_gold": "STRIPE_PRODUCT_EARLY_BIRD_GOLD",
    "regular": "STRIPE_PRODUCT_REGULAR_MEMBER",
    "gold": "STRIPE_PRODUCT_GOLD",
}


def _get_price_id_from_product(product_id):
    """Get the price ID to use for subscriptions from a Stripe Product ID. Uses default_price or first recurring price."""
    if not product_id:
        return None

    def _id_from_price(p):
        """Extract price id from Stripe Price object or dict."""
        if p is None:
            return None
        if isinstance(p, str) and p.startswith("price_"):
            return p
        return getattr(p, "id", None) or (p.get("id") if hasattr(p, "get") else None)

    def _has_recurring(p):
        """True if price has recurring (for subscriptions)."""
        if p is None:
            return False
        rec = getattr(p, "recurring", None) or (p.get("recurring") if hasattr(p, "get") else None)
        return bool(rec)

    try:
        # Retrieve without expand first: default_price is often returned as a string id
        product = stripe.Product.retrieve(product_id)
        default = product.get("default_price")
        price_id = _id_from_price(default)
        if price_id:
            return price_id

        # Optional: try with expand in case default_price was an object reference
        product = stripe.Product.retrieve(product_id, expand=["default_price"])
        default = product.get("default_price")
        price_id = _id_from_price(default)
        if price_id:
            return price_id

        # No default_price set on product: use first recurring price from product's prices
        prices = stripe.Price.list(product=product_id, active=True, limit=10)
        for p in prices.get("data", []):
            if _has_recurring(p):
                pid = _id_from_price(p)
                if pid:
                    return pid
        return None
    except stripe.error.StripeError:
        return None


def _count_active_subscriptions(price_id):
    """Return number of active subscriptions for the given Stripe price ID."""
    if not price_id:
        return None
    try:
        subs = stripe.Subscription.list(price=price_id, status="active", limit=100)
        return len(subs.get("data", []))
    except Exception:
        return None


def _get_user_membership(user_id):
    """Return the user's active membership if any (most recent by created_at)."""
    if not user_id:
        return None
    m = (
        Membership.query.filter_by(user_id=user_id, status="active")
        .order_by(Membership.created_at.desc())
        .first()
    )
    return m


def _get_user_latest_membership(user_id):
    """Return the user's most recent membership (any status), for showing ended/canceled state."""
    if not user_id:
        return None
    return (
        Membership.query.filter_by(user_id=user_id)
        .order_by(Membership.created_at.desc())
        .first()
    )


def _user_has_medical_school_access(user_id):
    """True if user has Gold/Early Bird Gold membership OR has purchased the medical school course product ($97)."""
    if not user_id:
        return False
    membership = _get_user_membership(user_id)
    if membership and membership.tier in ("gold", "early_bird_gold"):
        return True
    pid = _medical_school_course_product_id()
    if not pid:
        return False
    has_purchase = (
        OrderItem.query.join(Order)
        .filter(Order.user_id == user_id, OrderItem.product_id == pid)
        .first()
        is not None
    )
    return has_purchase


# Structure for medical school course: module number (1-based) -> (module_title, [lesson_titles])
# (module_title, module_description, [lesson_title, ...])
MEDICAL_SCHOOL_MODULES = [
    ("Building Your Foundation", "GPA, rigor, and the first two years. Setting yourself up without burning out.", ["Choosing your major and course load", "Study systems that scale", "When to start research and volunteering"]),
    ("MCAT Mastery", "Content review, practice exams, and test-day strategy. When to take it and how to improve.", ["Content review schedule", "Full-length strategy and review", "Test day and score release"]),
    ("Crafting Your Narrative", "Personal statement, activities, and the story that ties your application together.", ["Finding your theme", "Drafting the personal statement", "Activities and work/activities section"]),
    ("Letters & Relationships", "Choosing letter writers, when to ask, and how to make it easy for them to say yes.", ["Who to ask and how many", "Requesting the letter and providing materials", "Committee letters and packets"]),
    ("School List Strategy", "Reach, target, and safety. Building a list that fits your stats and your life.", ["Using MSAR and school missions", "How many schools to apply to", "Geography, cost, and fit"]),
    ("Secondaries That Stand Out", "Templates, themes, and how to turn the same experiences into school-specific answers.", ["Common secondary prompts", "Reusing and tailoring answers", "Timeline and staying sane"]),
    ("Interview Prep", "MMI, traditional, and virtual. Practice questions and how to show up as yourself.", ["MMI format and practice", "Traditional interview questions", "Virtual interview setup and mindset"]),
    ("The Waitlist & Beyond", "Letters of intent, updates, and staying sane while you wait. Planning for gap years.", ["Letters of intent and interest", "Update letters and when to send", "Gap year planning and reapplication"]),
]


def _tier_from_stripe_subscription(sub):
    """Infer tier from subscription's first item price/product. Returns None if unknown."""
    items = (sub or {}).get("items") or {}
    data = items.get("data") or []
    if not data:
        return None
    price = (data[0] or {}).get("price") or {}
    product = price.get("product")
    if isinstance(product, str) and product.startswith("prod_"):
        product_id = product
    elif isinstance(product, dict):
        product_id = product.get("id")
    else:
        product_id = getattr(product, "id", None)
    if not product_id:
        return None
    # PREMIUM_PRODUCT_KEYS: tier -> env key; env value is product_id
    for tier, env_key in PREMIUM_PRODUCT_KEYS.items():
        if os.environ.get(env_key, "").strip() == product_id:
            return tier
    return None


TIER_LABELS = {"early_bird_gold": "Early Bird Gold", "regular": "Regular Member", "gold": "Gold"}


def _sync_membership_from_checkout_session(session_id, user_id):
    """After payment redirect: create/update Membership from Stripe Checkout Session so the user sees 'Manage subscription' without waiting for the webhook."""
    if not session_id or not user_id:
        return
    try:
        s = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
        if s.get("mode") != "subscription":
            return
        meta = s.get("metadata") or {}
        if meta.get("user_id") != str(user_id):
            return
        sub_id = s.get("subscription")
        if not sub_id:
            return
        sub = sub_id if isinstance(sub_id, dict) else stripe.Subscription.retrieve(sub_id)
        sub_id = sub.get("id") if isinstance(sub, dict) else getattr(sub, "id", sub_id)
        cust_id = s.get("customer")
        tier = meta.get("tier") or "regular"
        period_end = None
        if sub.get("current_period_end"):
            period_end = datetime.utcfromtimestamp(sub["current_period_end"])
        elif hasattr(sub, "current_period_end") and sub.current_period_end:
            period_end = datetime.utcfromtimestamp(sub.current_period_end)
        existing = Membership.query.filter_by(stripe_subscription_id=sub_id).first()
        if existing:
            if existing.user_id is None:
                existing.user_id = user_id
                existing.link_code = None
                db.session.commit()
            return
        cancel_old_id = meta.get("cancel_subscription_id")
        if cancel_old_id:
            try:
                stripe.Subscription.delete(cancel_old_id)
            except stripe.error.StripeError:
                pass
        for old in Membership.query.filter_by(user_id=user_id, status="active").all():
            db.session.delete(old)
        db.session.add(Membership(
            user_id=user_id,
            stripe_subscription_id=sub_id,
            stripe_customer_id=cust_id,
            tier=tier,
            status="active",
            current_period_end=period_end,
        ))
        db.session.commit()
    except stripe.error.StripeError:
        pass
    except Exception:
        pass


@main.route("/premium", methods=["GET"])
def premium():
    membership = None
    latest_membership = None
    if current_user.is_authenticated:
        if request.args.get("success") == "1":
            flash("Thanks for subscribing! You can manage your subscription below.", "success")
            session_id = request.args.get("session_id")
            if session_id:
                _sync_membership_from_checkout_session(session_id, current_user.id)
        membership = _get_user_membership(current_user.id)
        latest_membership = _get_user_latest_membership(current_user.id)  # for "ended" message when no active
    product_id_early = os.environ.get(PREMIUM_PRODUCT_KEYS["early_bird_gold"], "").strip()
    price_id_early = _get_price_id_from_product(product_id_early) if product_id_early else None
    count = _count_active_subscriptions(price_id_early) if price_id_early else None
    early_bird_spots_left = (EARLY_BIRD_CAPACITY - count) if count is not None else None
    regular_price = os.environ.get("PREMIUM_REGULAR_MEMBER_PRICE", "20")
    form = PremiumCSRFForm()
    return render_template(
        "premium.html",
        form=form,
        membership=membership,
        latest_membership=latest_membership,
        tier_labels=TIER_LABELS,
        early_bird_spots_left=early_bird_spots_left,
        regular_member_price=regular_price,
    )


VALID_TIERS = ("early_bird_gold", "regular", "gold")


@main.route("/create-membership-checkout-session", methods=["POST"])
@login_required
def create_membership_checkout_session():
    tier = (request.form.get("tier") or "").strip()
    if tier not in VALID_TIERS:
        flash("Invalid membership tier.", "danger")
        return redirect(url_for("main.premium"))
    product_id = os.environ.get(PREMIUM_PRODUCT_KEYS.get(tier, ""), "").strip()
    if not product_id:
        flash("This membership is not set up yet. Add your Stripe product IDs to the server (.env) and try again.", "warning")
        return redirect(url_for("main.premium"))
    price_id = _get_price_id_from_product(product_id)
    if not price_id:
        flash("Could not get a subscription price for this product. Check the product in Stripe has a recurring price.", "warning")
        return redirect(url_for("main.premium"))
    if tier == "early_bird_gold":
        count = _count_active_subscriptions(price_id)
        if count is not None and count >= EARLY_BIRD_CAPACITY:
            flash("Early Bird Gold is sold out (10 spots filled).", "warning")
            return redirect(url_for("main.premium"))
    metadata = {"tier": tier, "user_id": str(current_user.id)}
    existing = _get_user_membership(current_user.id)
    if existing:
        metadata["cancel_subscription_id"] = existing.stripe_subscription_id
    try:
        success_url = url_for("main.premium", _external=True)
        if not success_url.endswith("/"):
            success_url = success_url.rstrip("/")
        success_url += "?session_id={CHECKOUT_SESSION_ID}&success=1"
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=url_for("main.premium", _external=True),
            metadata=metadata,
            client_reference_id=str(current_user.id),
            customer_email=current_user.email or None,
        )
        return redirect(checkout_session.url, code=303)
    except stripe.error.StripeError as e:
        flash(f"Could not start checkout: {str(e)}", "danger")
        return redirect(url_for("main.premium"))


@main.route("/premium/portal", methods=["GET", "POST"])
@login_required
def premium_portal():
    """Redirect to Stripe Customer Billing Portal to manage/cancel subscription."""
    membership = _get_user_membership(current_user.id)
    if not membership or not membership.stripe_customer_id:
        flash("No active subscription found.", "warning")
        return redirect(url_for("main.premium"))
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=membership.stripe_customer_id,
            return_url=url_for("main.premium", _external=True),
        )
        return redirect(portal_session.url, code=303)
    except stripe.error.StripeError as e:
        flash(f"Could not open billing portal: {str(e)}", "danger")
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
    """Redirect to products (shop tab goes directly to products)."""
    return redirect(url_for('main.products'))

@main.route('/orders')
@login_required  # Ensure the user is logged in
def orders():
    # Fetch orders for the logged-in user
    user_orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('orders.html', user=current_user, orders=user_orders)

@main.route("/products")
def products():
    try:
        # Exclude course products from shop (courses are on their own page)
        products = Product.query.filter(or_(Product.category.is_(None), Product.category != "Course")).all()
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

@main.route('/account', methods=['GET'])
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


def _password_reset_serializer():
    from itsdangerous import URLSafeTimedSerializer
    secret = current_app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY") or "change-me"
    return URLSafeTimedSerializer(secret, salt="password-reset")


@main.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data.strip().lower()).first()
        if user:
            ser = _password_reset_serializer()
            token = ser.dumps({"user_id": user.id}, salt="password-reset")
            reset_url = url_for("main.reset_password", token=token, _external=True)
            html = f"<p>You requested a password reset. Click the link below to set a new password (valid for 1 hour):</p><p><a href=\"{reset_url}\">{reset_url}</a></p><p>If you didn't request this, you can ignore this email.</p>"
            sent = send_email(to=user.email, subject="Reset your password", html=html)
            if sent:
                flash("Check your email for a link to reset your password.", "success")
            else:
                flash("We couldn't send the email. Please try again later or contact support.", "danger")
        else:
            # Don't reveal whether the email exists
            flash("If that email is registered, you'll receive a reset link shortly.", "success")
        return redirect(url_for("main.login"))
    return render_template("forgot_password.html", title="Forgot password", form=form)


@main.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    token = request.args.get("token") or request.form.get("token")
    if not token:
        flash("Invalid or missing reset link.", "danger")
        return redirect(url_for("main.forgot_password"))
    from itsdangerous import BadSignature, SignatureExpired
    ser = _password_reset_serializer()
    try:
        payload = ser.loads(token, salt="password-reset", max_age=3600)
        user_id = payload.get("user_id")
    except (BadSignature, SignatureExpired):
        flash("That reset link is invalid or has expired. Please request a new one.", "danger")
        return redirect(url_for("main.forgot_password"))
    user = User.query.get(user_id) if user_id else None
    if not user:
        flash("Invalid reset link.", "danger")
        return redirect(url_for("main.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        db.session.commit()
        flash("Your password has been updated. You can log in now.", "success")
        return redirect(url_for("main.login"))
    return render_template("reset_password.html", title="Reset password", form=form, token=token)

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

    # Create Stripe checkout session (success_url includes session_id so we can create order on redirect without webhook)
    success_url = url_for('main.payment_success', _external=True)
    if not success_url.endswith('/'):
        success_url = success_url.rstrip('/')
    success_url += '?session_id={CHECKOUT_SESSION_ID}'
    session_data = stripe.checkout.Session.create(
        metadata={
            'user_id': str(user_id) if user_id else '',
            'cart': json.dumps(cart)
        },
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=success_url,
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


def _set_if_attr(obj, name, value):
    if hasattr(obj, name):
        setattr(obj, name, value)


def _upsert_order_and_reduce_stock(meta, session_id=None, pi_id=None):
    """Create or update order and reduce inventory from Stripe session metadata. Idempotent by session_id."""
    raw_cart = (meta or {}).get("cart", "{}")
    try:
        cart = json.loads(raw_cart) if isinstance(raw_cart, str) else (raw_cart or {})
    except Exception:
        cart = {}

    user_id = (meta or {}).get("user_id")
    if isinstance(user_id, str) and user_id.isdigit():
        user_id = int(user_id)
    else:
        user_id = None

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
        _set_if_attr(order, "stripe_session_id", session_id)
        _set_if_attr(order, "payment_intent_id", pi_id)
        _set_if_attr(order, "status", "paid")
        _set_if_attr(order, "paid_at", datetime.utcnow())
        _set_if_attr(order, "inventory_reduced", False)
        _set_if_attr(order, "confirmation_sent", False)
        db.session.add(order)
        db.session.flush()

    existing = {oi.product_id: oi for oi in OrderItem.query.filter_by(order_id=order.id).all()}
    total = 0.0

    for pid_str, qty in (cart or {}).items():
        try:
            pid = int(pid_str)
            qty = int(qty)
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
    _set_if_attr(order, "status", "paid")
    _set_if_attr(order, "inventory_reduced", True)
    db.session.commit()
    return order.id


@main.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    import os, traceback, requests
    from sqlalchemy.exc import SQLAlchemyError
    from SS.models import Membership as M

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

    try:
        if etype == "checkout.session.completed":
            s = event["data"]["object"]
            mode = s.get("mode")
            if mode == "subscription":
                sub_id = s.get("subscription")
                cust_id = s.get("customer")
                meta = s.get("metadata") or {}
                user_id_str = meta.get("user_id")
                tier = meta.get("tier") or "regular"
                if sub_id:
                    existing = M.query.filter_by(stripe_subscription_id=sub_id).first()
                    if not existing:
                        sub = stripe.Subscription.retrieve(sub_id)
                        period_end = None
                        if sub.get("current_period_end"):
                            period_end = datetime.utcfromtimestamp(sub["current_period_end"])
                        if user_id_str and user_id_str.isdigit():
                            user_id = int(user_id_str)
                            cancel_old_id = meta.get("cancel_subscription_id")
                            if cancel_old_id:
                                try:
                                    stripe.Subscription.delete(cancel_old_id)
                                except stripe.error.StripeError:
                                    pass
                            for old in M.query.filter_by(user_id=user_id, status="active").all():
                                db.session.delete(old)
                            db.session.add(M(
                                user_id=user_id,
                                stripe_subscription_id=sub_id,
                                stripe_customer_id=cust_id,
                                tier=tier,
                                status="active",
                                current_period_end=period_end,
                            ))
                            db.session.commit()
                return "ok", 200
            if s.get("payment_status") == "paid":
                order_id = _upsert_order_and_reduce_stock(
                    meta=s.get("metadata") or {},
                    session_id=s.get("id"),
                    pi_id=s.get("payment_intent"),
                )
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

        if etype == "customer.subscription.updated":
            sub = event["data"]["object"]
            sub_id = sub.get("id")
            m = M.query.filter_by(stripe_subscription_id=sub_id).first()
            if m:
                m.status = sub.get("status", m.status)
                if sub.get("current_period_end"):
                    m.current_period_end = datetime.utcfromtimestamp(sub["current_period_end"])
                if sub.get("customer"):
                    m.stripe_customer_id = sub["customer"]
                tier_from_stripe = _tier_from_stripe_subscription(sub)
                if tier_from_stripe:
                    m.tier = tier_from_stripe
                m.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
                db.session.commit()
            return "ok", 200

        if etype == "customer.subscription.deleted":
            sub = event["data"]["object"]
            sub_id = sub.get("id")
            m = M.query.filter_by(stripe_subscription_id=sub_id).first()
            if m:
                m.status = "canceled"
                m.canceled_at = datetime.utcnow()
                m.cancel_at_period_end = False
                db.session.commit()
            return "ok", 200

        if etype == "payment_intent.succeeded":
            # we’ll still reduce inventory here (idempotent) but skip email
            pi = event["data"]["object"]
            _upsert_order_and_reduce_stock(meta=pi.get("metadata") or {}, pi_id=pi.get("id"))
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
    # Create order from Stripe session on redirect (works locally without webhook; idempotent with webhook)
    session_id = request.args.get('session_id')
    if session_id:
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.get('mode') == 'payment' and s.get('payment_status') == 'paid':
                _upsert_order_and_reduce_stock(
                    s.get('metadata') or {},
                    session_id=s.get('id'),
                    pi_id=s.get('payment_intent'),
                )
        except stripe.error.StripeError:
            pass
    return render_template('payment_success.html')

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
    """Redirect to products (singles search page removed)."""
    return redirect(url_for('main.products'))

@main.route('/store/card-search', methods=['GET'])
def store_card_search():
    """Singles search removed; return empty results."""
    return jsonify([])


@main.route('/courses')
def courses():
    """Courses listing page."""
    return render_template('courses.html')


@main.route('/free-resources')
def free_resources():
    """Free resources listing page (guides, downloads, etc.)."""
    return render_template('free_resources.html')


# Product name must match SS/add_medical_school_course_product.py
MEDICAL_SCHOOL_COURSE_PRODUCT_NAME = "Getting into Medical School (Course)"


def _medical_school_course_product_id():
    """Return the product id for the $97 course if configured, else None. Uses env var or DB lookup by name."""
    raw = os.environ.get("MEDICAL_SCHOOL_COURSE_PRODUCT_ID", "").strip()
    try:
        pid = int(raw) if raw else None
    except ValueError:
        pid = None
    if pid is not None:
        return pid
    # Fallback: product exists in DB but env not set — look up by name
    p = Product.query.filter_by(product_name=MEDICAL_SCHOOL_COURSE_PRODUCT_NAME).first()
    return p.id if p else None


@main.route('/courses/medical-school')
def course_medical_school():
    """Getting into Medical School. Access via Gold/Early Bird Gold or one-time $97 purchase."""
    can_access = _user_has_medical_school_access(current_user.id) if current_user.is_authenticated else False
    course_product_id = _medical_school_course_product_id()
    return render_template(
        'course_medical_school.html',
        can_access=can_access,
        modules_lessons=MEDICAL_SCHOOL_MODULES,
        course_product_id=course_product_id,
    )


@main.route('/courses/medical-school/buy', methods=['GET', 'POST'])
def course_medical_school_buy():
    """Add the $97 course product to cart and redirect to cart. Requires login."""
    if not current_user.is_authenticated:
        flash("Log in to purchase the course.", "warning")
        return redirect(url_for("main.login", next=url_for("main.course_medical_school")))
    pid = _medical_school_course_product_id()
    if not pid:
        flash("Course purchase is not configured.", "warning")
        return redirect(url_for("main.course_medical_school"))
    product = Product.query.get(pid)
    if not product:
        flash("Course product not found.", "warning")
        return redirect(url_for("main.course_medical_school"))
    add_to_cart(product.id, 1)
    check_free_booster_pack()
    flash("Course added to cart. Complete checkout to get access.", "success")
    return redirect(url_for("main.cart"))


@main.route('/courses/medical-school/lesson/<int:module_num>/<int:lesson_num>')
def course_medical_school_lesson(module_num, lesson_num):
    """Show a single lesson (video + title). Only if user has course access."""
    if not current_user.is_authenticated:
        flash("Log in to access course lessons.", "warning")
        return redirect(url_for("main.login", next=request.url))
    if not _user_has_medical_school_access(current_user.id):
        flash("You need Gold membership or the one-time course purchase to view lessons.", "warning")
        return redirect(url_for("main.course_medical_school"))
    if module_num < 1 or module_num > len(MEDICAL_SCHOOL_MODULES):
        return redirect(url_for("main.course_medical_school"))
    module_title, _description, lesson_titles = MEDICAL_SCHOOL_MODULES[module_num - 1]
    if lesson_num < 1 or lesson_num > len(lesson_titles):
        return redirect(url_for("main.course_medical_school"))
    lesson_title = lesson_titles[lesson_num - 1]
    return render_template(
        'course_lesson.html',
        course_title="Getting into Medical School",
        module_num=module_num,
        module_title=module_title,
        lesson_num=lesson_num,
        lesson_title=lesson_title,
        total_modules=len(MEDICAL_SCHOOL_MODULES),
        lessons_in_module=len(lesson_titles),
    )


@main.route('/cv')
def cv():
    """CV / resume page."""
    return render_template('cv.html')

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

