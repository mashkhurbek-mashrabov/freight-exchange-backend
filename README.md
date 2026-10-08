# Freight Exchange Backend

REST API backend for a mobile freight exchange platform (load board). Shippers publish loads with multi-stop routes, carriers register vehicles in a garage, search loads, submit offers, negotiate prices, and complete orders. Built with Django 5, Django REST Framework, PostgreSQL, Redis, and Celery, with interactive Swagger / OpenAPI documentation.

## Architecture

```mermaid
flowchart LR
  M[Mobile app] -->|HTTPS JSON + JWT| N[Nginx or platform proxy]
  N --> W[Django + DRF - gunicorn]
  W --> P[(PostgreSQL)]
  W --> R[(Redis)]
  W -. OpenAPI .-> S[Swagger UI /api/docs/]
  R --> C[Celery worker]
  B[Celery beat] --> R
  C --> P
  C -. later .-> F[FCM push]
  A[Django admin: moderators] --> W
```

## Quick Start

1. **Clone and configure environment:**
   ```bash
   cp .env.example .env
   ```

2. **Start Docker services:**
   ```bash
   docker compose up --build
   ```

3. **Seed demo data:**
   ```bash
   make seed
   ```

4. **Access the API and Swagger documentation:**
   - Swagger UI: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
   - ReDoc: [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)
   - OpenAPI Schema: [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)
   - Health check: [http://localhost:8000/health/](http://localhost:8000/health/)
   - Django Admin: [http://localhost:8000/admin/](http://localhost:8000/admin/)

## Swagger Test Script

### Demo Accounts
- **Carrier:** `+998900000001` (Verified carrier with tractor and trailer, OTP `000000`)
- **Shipper:** `+998900000002` (Verified shipper owning seeded loads, OTP `000000`)

### Verification Steps in Swagger UI
1. Call `POST /api/v1/auth/otp/request` with body:
   ```json
   {
     "phone": "+998900000001"
   }
   ```
   Expected response: `204 No Content`.
2. Call `POST /api/v1/auth/otp/verify` with body:
   ```json
   {
     "phone": "+998900000001",
     "code": "000000"
   }
   ```
   Copy the `access` token from the response.
3. Click the **Authorize** button at the top of Swagger UI, enter the Bearer access token, and save.
4. Call `GET /api/v1/loads` to retrieve seeded loads.

## Environment Variables

| Variable | Description | Default / Dev Value |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Active Django settings module | `config.settings.dev` |
| `SECRET_KEY` | Cryptographic signing key | `change-me-insecure-dev-key` |
| `DEBUG` | Enable Django debug mode | `True` |
| `ALLOWED_HOSTS` | Allowed host headers | `*` |
| `DATABASE_URL` | PostgreSQL connection string | `postgres://freight:freight@db:5432/freight` |
| `REDIS_URL` | Redis connection string (cache & Celery broker) | `redis://redis:6379/0` |
| `CORS_ALLOWED_ORIGINS` | Allowed origins for CORS | `http://localhost:3000` |
| `JWT_ACCESS_MINUTES` | Access token lifespan in minutes | `30` |
| `JWT_REFRESH_DAYS` | Refresh token lifespan in days | `30` |
| `SMS_BACKEND` | SMS backend class path | `apps.accounts.sms.ConsoleSmsBackend` |
| `OTP_DEV_CODE` | Fixed OTP bypass code for local testing | `000000` |
| `POSTGRES_DB` | PostgreSQL database name | `freight` |
| `POSTGRES_USER` | PostgreSQL username | `freight` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `freight` |

## Makefile Targets

| Target | Command | Description |
|---|---|---|
| `make up` | `docker compose up --build -d` | Build images and start all containers in background |
| `make down` | `docker compose down` | Stop and remove running containers |
| `make logs` | `docker compose logs -f` | Tail logs for all containers |
| `make migrate` | `docker compose exec web python manage.py migrate` | Run database migrations |
| `make makemigrations` | `docker compose exec web python manage.py makemigrations` | Create new database migration files |
| `make references` | `docker compose exec web python manage.py load_references` | Load reference data idempotently |
| `make seed` | `docker compose exec web python manage.py seed_demo` | Load demo seed data |
| `make test` | `docker compose exec web pytest -q` | Run tests with pytest inside web container |
| `make lint` | `docker compose exec web ruff check .` | Run ruff linter inside web container |
| `make shell` | `docker compose exec web python manage.py shell` | Open Django interactive shell |
| `make schema` | `docker compose exec web python manage.py spectacular --validate --fail-on-warn --file schema.yml` | Validate and dump OpenAPI schema |

## Reference Data

The platform relies on core reference data loaded from JSON fixtures:
- **Countries**: ISO 2-letter codes, localized names (`uz`, `ru`, `en`), and flag URLs.
- **Currencies**: Supported transaction currencies (`UZS`, `USD`, `EUR`, `RUB`, `KZT`, `AED`).
- **Vehicle Types**: Tractor and trailer body and vehicle classifications identified by unique `code`.
- **Exchange Rates**: Indicative placeholder currency conversion rates, managed by administrators in Django admin.

Reference data is loaded automatically on container start when migrations run, and can also be triggered via `make references` (or `python manage.py load_references`). The command is idempotent and never overwrites administrator edits. To refresh existing rows back to fixture defaults, use the `--force` flag (`python manage.py load_references --force`). Reference caches are invalidated automatically after loading.

## Local Development (Non-Docker)

1. **Create and activate Python 3.12 virtual environment:**
   ```bash
   uv venv --python 3.12 .venv
   source .venv/bin/activate
   uv pip install -r requirements/dev.txt
   ```

2. **Configure environment variables:**
   ```bash
   export DJANGO_SETTINGS_MODULE=config.settings.dev
   export DATABASE_URL=postgres://freight:freight@localhost:5432/freight
   export REDIS_URL=redis://localhost:6379/0
   export SECRET_KEY=change-me-insecure-dev-key
   export DEBUG=True
   export ALLOWED_HOSTS=*
   export CORS_ALLOWED_ORIGINS=http://localhost:3000
   export JWT_ACCESS_MINUTES=30
   export JWT_REFRESH_DAYS=30
   export SMS_BACKEND=apps.accounts.sms.ConsoleSmsBackend
   export OTP_DEV_CODE=000000
   ```

3. **Run database migrations and start development server:**
   ```bash
   python manage.py migrate
   python manage.py runserver 0.0.0.0:8000
   ```

4. **Run tests and linting:**
   ```bash
   ruff check .
   python manage.py spectacular --validate --fail-on-warn
   pytest -q
   ```

## Phase Status

- [x] Phase 0: Repo, skeleton, Docker, Swagger
- [x] Phase 1: Accounts and OTP auth
- [x] Phase 2: Reference data
- [x] Phase 3: Garage
- [x] Phase 4: Loads and routes
- [x] Phase 5: Offers
- [x] Phase 6: Orders and ratings
- [x] Phase 7: Notifications and Celery jobs
- [x] Phase 8: Seed data, hardening, CI, docs

Plan-to-code mapping: see [docs/PLAN_COVERAGE.md](docs/PLAN_COVERAGE.md).

## Decisions

Ambiguities in `plan.md` resolved with the simplest option that passes the acceptance checks:

- **Tests need PostgreSQL** (Rating.reasons is an `ArrayField`). Tests run with `config.settings.test`
  (LocMem cache, eager Celery, fast hashers); counters/rate limits use Django's cache API, not redis-py.
- **Load list "city".** Route points have only `address` and `country`; list items expose
  `origin`/`destination` as `{country, address}` (lowest-seq loading point, highest-seq unloading point).
- **Reference endpoints** (`/countries`, `/currencies`, `/vehicle-types`, `/exchange-rates`) are not
  paginated (small lists), cached 1 hour, cache invalidated on admin save/delete.
- **`/loads`** serves both `GET` (board of active loads) and `POST` (create draft) from one view.
- **Offers.** An offer by a carrier uses `proposer=carrier, recipient=shipper`; a counter flips both and
  marks the old row `countered`. Phone numbers are not exposed on offers, only on orders (parties only).
- **Order cancel.** Requires `note` as the cancel reason; allowed from `created|received` only.
- **Load completes** when the number of completed orders equals `trucks_needed`.
- **OTP.** Code hashed with HMAC-SHA256 (key `SECRET_KEY`); `OTP_DEV_CODE` is accepted without a stored
  code and is forced empty in `config.settings.prod`.
- **Admin "Mark verified"** lives in `accounts.services.mark_verified` and sends `account_verified`.
- **Beat** schedule is in `CELERY_BEAT_SCHEDULE` (no django-celery-beat DB scheduler).
- **Throttling**: anon 60/min, user 600/min, stricter scopes on OTP endpoints.
- **Uploads**: images <= 5 MB (jpeg/png/webp), documents <= 10 MB; validated in serializers.
