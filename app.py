# app.py - load .env first so USE_SQLITE/DATABASE_URL apply to "flask db upgrade" too
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

import os
from flask import redirect, url_for, request
from flask_login import current_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView

from SS import create_app
from SS.models import db, Product, User, Order, OrderItem

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

    def is_accessible(self):
        return _is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("main.login", next=request.url))

# Create admin with a secured index view
admin = Admin(
    app,
    name="Admin Panel",
    template_mode="bootstrap4",
    index_view=SecureAdminIndexView(url="/admin", name="Dashboard"),
)

# Secure all model views
admin.add_view(SecureModelView(User, db.session))
admin.add_view(SecureModelView(Product, db.session))
admin.add_view(SecureModelView(Order, db.session))
admin.add_view(SecureModelView(OrderItem, db.session))

if __name__ == "__main__":
    # Local dev; Render uses gunicorn
    app.run(debug=True)

