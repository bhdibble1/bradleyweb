# Deploying the MTGstore Web App

This app is a Flask app with SQLAlchemy, Stripe, and Flask-Admin. It’s set up to deploy on **Render** (or similar platforms that use a Procfile).

## 1. Prepare the repo

- Ensure `.env` is **not** committed (it’s in `.gitignore`). Use the platform’s **Environment** / **Config vars** for secrets.
- Commit and push:
  - `Procfile` (uses `gunicorn "app:app"`)
  - `runtime.txt` (e.g. `python-3.11.9`)
  - `requirements.txt`
  - `migrations/` (so DB migrations run on deploy)

## 2. Deploy on Render

1. **New → Web Service** and connect your repo.
2. **Build & deploy**
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** leave empty (Render uses the `Procfile` `web` process).
   - **Release command (optional but recommended):**  
     `flask db upgrade`  
     Set **Environment** (see below) so `FLASK_APP=app:app` is set for the release command (or add it in the Render dashboard for the release step only).

3. **Environment variables**  
   Add these in the Render dashboard (Environment tab). Use strong, production values; never commit them.

   **Required**

   | Variable | Description |
   |----------|--------------|
   | `SECRET_KEY` | Random secret for sessions (e.g. `openssl rand -hex 32`) |
   | `DATABASE_URL` | Postgres connection URL (Render provides this if you add a Postgres DB and link it) |
   | `STRIPE_SECRET_KEY` | Stripe secret key (live if production) |
   | `STRIPE_PUBLIC_KEY` | Stripe publishable key (live if production) |

   **Do not set** `USE_SQLITE` in production (or set it to `0`). When `DATABASE_URL` is set and `USE_SQLITE` is not `1`, the app uses Postgres.

   **Optional / feature-related**

   | Variable | Description |
   |----------|--------------|
   | `ADMIN_EMAIL` | Email that can access `/admin` (default: Bhdibble@gmail.com) |
   | `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret for payment webhooks |
   | `PRINTFUL_API_KEY` | For Printful integration |
   | `TASK_TOKEN` | If you use task/automation endpoints |
   | `RESEND_API_KEY` | For Resend email |
   | `FROM_EMAIL` / `FROM_NAME` | Sender for emails |
   | `GUIDE_DOWNLOAD_URL` / `GUIDE_BOOK_IMAGE_URL` | Links/images for guide/book |
   | `PREMIUM_REGULAR_MEMBER_PRICE` | Price for regular member tier |
   | Stripe product IDs | e.g. `STRIPE_PRODUCT_EARLY_BIRD_GOLD`, `STRIPE_PRODUCT_REGULAR_MEMBER`, `STRIPE_PRODUCT_GOLD` (if your code reads them from env) |

4. **Database**
   - In Render: **New → PostgreSQL** and create a database.
   - Link it to your Web Service; Render will set `DATABASE_URL` automatically.
   - If you use another Postgres host, set `DATABASE_URL` manually (e.g. `postgresql://user:pass@host:5432/dbname`).

5. **Migrations**
   - Ensure **Release command** is `flask db upgrade` and that the app is loadable (e.g. set `FLASK_APP=app:app` in Environment so the release step uses your app).
   - On first deploy, this creates/updates tables; on later deploys it applies new migration files.

6. **Stripe webhooks**
   - In Stripe Dashboard → Developers → Webhooks, add an endpoint pointing to your deployed URL (e.g. `https://your-service.onrender.com/your-webhook-path`).
   - Set `STRIPE_WEBHOOK_SECRET` to the webhook’s signing secret.

## 3. After deploy

- Open `https://<your-service>.onrender.com` and confirm the site loads.
- Log in with the admin user (same email as `ADMIN_EMAIL`) and open `/admin` to confirm Admin works.
- Test a Stripe payment (test mode first) and confirm the webhook is called if you use it.

## 4. Optional: Railway or other platforms

- **Railway:** Add a **Web Service**, set start command to `gunicorn "app:app"` (or use a Procfile if supported). Add a Postgres plugin and set `DATABASE_URL`. Set the same env vars as above and run `flask db upgrade` in a one-off command or release step.
- **Heroku:** Same idea: `Procfile` and `runtime.txt` work; use Heroku Postgres and Config Vars for all secrets and run `flask db upgrade` (e.g. in a release phase or manually).

## 5. Security checklist

- [ ] `SECRET_KEY` is random and not the default dev value.
- [ ] `DATABASE_URL` is set and `USE_SQLITE` is not enabled in production.
- [ ] Stripe keys are live keys only in production; webhook secret matches the deployed URL.
- [ ] No `.env` or secrets are committed to the repo.
