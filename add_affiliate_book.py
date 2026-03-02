"""One-off: add an affiliate book. Run: pipenv run python add_affiliate_book.py"""
from app import app
from SS.models import db, AffiliateBook

URL = "https://amzn.to/46BcZjW"

with app.app_context():
    if AffiliateBook.query.filter_by(amazon_url=URL).first():
        print("Already added:", URL)
    else:
        b = AffiliateBook(
            title="Book (edit title in Admin)",
            author="",
            amazon_url=URL,
            active=True,
            sort_order=0,
        )
        db.session.add(b)
        db.session.commit()
        print("Added:", b.title, "→", b.amazon_url)
