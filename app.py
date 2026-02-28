# app.py - load .env first so USE_SQLITE/DATABASE_URL apply to "flask db upgrade" too
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

import inspect
import os
from flask import redirect, url_for, request
from flask_login import current_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView

# Flask-Admin 2.x removed template_mode; 1.x has it. Only pass args the installed version accepts.
_admin_kw = {}
if "template_mode" in inspect.signature(Admin.__init__).parameters:
    _admin_kw["template_mode"] = "bootstrap4"
else:
    try:
        from flask_admin.theme import Bootstrap4Theme
        _admin_kw["theme"] = Bootstrap4Theme()
    except ImportError:
        try:
            from flask_admin.bootstrap4 import Bootstrap4Theme
            _admin_kw["theme"] = Bootstrap4Theme()
        except ImportError:
            pass  # 2.x default is Bootstrap4

from SS import create_app
from SS.models import db, Product, User, Order, OrderItem, Membership

app = create_app()

# Configure who can access /admin (env wins; falls back to your email)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "Bhdibble@gmail.com").lower()

def _is_admin() -> bool:
    return current_user.is_authenticated and getattr(current_user, "email", "").lower() == ADMIN_EMAIL

class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return _is_admin()

    def inaccessible_callback(self, name, **kwargs):
        # Redirect non-admins to login; preserve destination
        return redirect(url_for("main.login", next=request.url))

class SecureModelView(ModelView):
    # Nice defaults; optional
    can_view_details = True
    page_size = 50
    can_edit = True
    can_create = True
    can_delete = True

    def is_accessible(self):
        return _is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("main.login", next=request.url))


# Create admin with a secured index view (Flask-Admin 2.x uses theme=, 1.x uses template_mode=)
admin = Admin(
    app,
    name="Admin Panel",
    index_view=SecureAdminIndexView(url="/admin", name="Dashboard"),
    **_admin_kw,
)

# Secure all model views (no custom form_columns for Product to avoid WTForms flags bug)
admin.add_view(SecureModelView(User, db.session))
admin.add_view(SecureModelView(Product, db.session))
admin.add_view(SecureModelView(Order, db.session))
admin.add_view(SecureModelView(OrderItem, db.session))
admin.add_view(SecureModelView(Membership, db.session))

if __name__ == "__main__":
    # Local dev; Render uses gunicorn
    app.run(debug=True)

