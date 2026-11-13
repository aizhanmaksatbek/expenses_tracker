# expenses_tracker

Personal expense tracker built with FastAPI, Jinja2, HTMX, PostgreSQL, and SQLAlchemy.

## Local development

Copy `.env.example` to `.env` if running the app outside Docker. Start the application and
PostgreSQL with:

```sh
docker compose up --build
```

The app is available at <http://localhost:8000>. Database migrations run when the container
starts. The health endpoint is <http://localhost:8000/health>.

Create an account at `/register`, then add and manage expenses from the dashboard. New accounts
start with Food, Transport, Housing, Utilities, Health, Shopping, and Other categories; users
can also add categories. The quick-entry form defaults the currency to MYR and the date to today.
Each user's expenses and categories are scoped to their authenticated session.
The dashboard summarizes spending by currency and category, and plots a date-range trend line for
each currency; its default range is the current month.

The JSON expense endpoints are `GET/POST /expenses` and `GET/PUT/DELETE /expenses/{id}`.
Mutating browser-session requests require the session CSRF token (`X-CSRF-Token` for JSON).

## Tests and lint

```sh
pip install -e ".[dev]"
pytest
ruff check .
```
