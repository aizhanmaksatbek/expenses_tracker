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

GitHub Actions has separate CI and CD workflows. CI runs lint, tests, and a Docker build on pushes
and pull requests. CD runs only after a successful CI push to `main` and is skipped until the
`DEPLOY_AWS` repository variable is set to `true`. After creating the AWS resources, configure these
repository settings:

- Variable `AWS_REGION`
- Variable `ECR_REPOSITORY`
- Variable `EC2_INSTANCE_ID`
- Variable `DEPLOY_AWS` set to `true`
- Secret `AWS_ROLE_ARN` for a GitHub OIDC role that can push to ECR and send/poll SSM commands

The EC2 instance must be managed by Systems Manager, have Docker, AWS CLI, and `curl` installed, and
have an instance role that can pull from ECR. Create `/etc/expenses-tracker/app.env` on the instance
with production `DATABASE_URL` and `ENVIRONMENT=production`, and restrict its permissions (for
example, `chmod 600 /etc/expenses-tracker/app.env`). Point `DATABASE_URL` to a persistent PostgreSQL
database, not the local Compose database. The container listens on port 8000. Restrict the GitHub
OIDC role trust to this repository's `main` branch and scope its ECR/SSM permissions to the deploy
repository and target instance.
