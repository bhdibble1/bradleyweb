"""
One-off script: add canceled_at and cancel_at_period_end to membership table if missing.
Run from project root:  python add_membership_columns.py
Uses only stdlib so it works without activating the project venv.
Use this if flask db upgrade didn't apply the membership migration.
"""
import os
import sqlite3

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base, "instance", "app.sqlite")
    if not os.path.isfile(db_path):
        print(f"Database not found: {db_path}")
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(membership)")
    columns = [row[1] for row in cur.fetchall()]
    if "canceled_at" not in columns:
        cur.execute("ALTER TABLE membership ADD COLUMN canceled_at DATETIME")
        conn.commit()
        print("Added column: membership.canceled_at")
    else:
        print("Column membership.canceled_at already exists.")
    if "cancel_at_period_end" not in columns:
        cur.execute("ALTER TABLE membership ADD COLUMN cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0")
        conn.commit()
        print("Added column: membership.cancel_at_period_end")
    else:
        print("Column membership.cancel_at_period_end already exists.")
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
