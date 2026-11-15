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

## CI/CD

GitHub Actions has separate CI and CD workflows. CI runs lint, tests, and a Docker build on pushes and pull requests.

`SSH_HOST`\
`SSH_PRIVATE_KEY`\
`SSH_USERNAME`

## Features

- Dashboard with KPIs, change vs. previous period, top category, donut charts and spending trend
- Range presets (this month, last month, last 30 days, YTD, last 12 months)
- Monthly budgets per category with progress bars and over-budget alerts
- CSV export of filtered expenses (`/expenses/export.csv`)
- Dark mode, client-side search, toast notifications
- `/health` endpoint that checks the database

## Demo data

```bash
alembic upgrade head
python -m app.scripts.seed   # login: demo / DemoPassword123!
```
