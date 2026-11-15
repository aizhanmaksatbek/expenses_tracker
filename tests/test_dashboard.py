from tests.test_expenses import create_expense, register_and_login


def _category_id(client, name):
    return next(c["id"] for c in client.get("/categories").json() if c["name"] == name)


def test_health_checks_database(client):
    assert client.get("/health").status_code == 200


def test_category_percentages_are_share_of_total(client):
    token = register_and_login(client, username="share")
    create_expense(client, token, amount="75.00")
    create_expense(client, token, amount="25.00", category_id=_category_id(client, "Transport"))
    response = client.get("/?start_date=2026-11-01&end_date=2026-11-30")
    assert response.status_code == 200
    assert "75%" in response.text
    assert "25%" in response.text
    assert "Top category" in response.text


def test_preset_range_renders(client):
    register_and_login(client, username="preset")
    response = client.get("/?preset=last_30")
    assert response.status_code == 200
    assert "Last 30 days" in response.text


def test_csv_export_requires_login_and_escapes_formulas(client):
    assert client.get("/expenses/export.csv", follow_redirects=False).status_code in (303, 401)
    token = register_and_login(client, username="csv")
    create_expense(client, token, merchant='=HYPERLINK("x")')
    response = client.get("/expenses/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK" in response.text


def test_budget_lifecycle_and_ownership(client):
    token = register_and_login(client, username="budgeter")
    category_id = _category_id(client, "Food")
    create_expense(client, token, amount="90.00")
    form = {"csrf_token": token, "category_id": category_id, "currency": "MYR", "amount": "100"}
    response = client.post("/budgets", data=form, follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/?start_date=2026-11-01&end_date=2026-11-30")
    assert "Almost there" in page.text
    client.post("/budgets", data={**form, "amount": "50"}, follow_redirects=False)
    page = client.get("/?start_date=2026-11-01&end_date=2026-11-30")
    assert "Over budget" in page.text

    bad = client.post("/budgets", data={**form, "amount": "-1"}, follow_redirects=False)
    assert "budget_error" in bad.headers["location"]

    other = register_and_login(client, username="intruder")
    foreign = client.post(
        "/budgets", data={**form, "csrf_token": other}, follow_redirects=False
    )
    assert "budget_error" in foreign.headers["location"]
