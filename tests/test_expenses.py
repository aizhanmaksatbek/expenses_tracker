from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def create_expense(client: TestClient, csrf_token: str, **overrides):
    categories = client.get("/categories")
    assert categories.status_code == 200
    category_id = next(item["id"] for item in categories.json() if item["name"] == "Food")
    payload = {
        "amount": "18.75",
        "currency": "MYR",
        "category_id": category_id,
        "expense_date": "2026-11-12",
        "merchant": "Lunch Cafe",
        "description": "Lunch",
        "payment_method": "e_wallet",
        "notes": "Team lunch",
    }
    payload.update(overrides)
    response = client.post(
        "/expenses",
        json=payload,
        headers={"X-CSRF-Token": csrf_token},
    )
    return response, category_id


def test_create_expense_and_list_only_current_users_expenses(client: TestClient):
    csrf_token = register_and_login(client)

    response, category_id = create_expense(client, csrf_token)

    assert response.status_code == 201
    created = response.json()
    assert created["amount"] == "18.75"
    assert created["currency"] == "MYR"
    assert created["category_id"] == category_id
    assert created["category_name"] == "Food"
    assert created["user_id"]
    assert created["expense_date"] == "2026-11-12"
    assert client.get("/expenses").json() == [created]


@pytest.mark.parametrize("amount", ["0", "-1", "-0.01", "10000000000.00"])
def test_rejects_invalid_amounts(client: TestClient, amount: str):
    csrf_token = register_and_login(client)

    response, _ = create_expense(client, csrf_token, amount=amount)

    assert response.status_code == 422


def test_rejects_missing_required_fields(client: TestClient):
    csrf_token = register_and_login(client)

    response = client.post(
        "/expenses",
        json={"expense_date": "2026-11-12"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_create_defaults_and_expense_filters(client: TestClient):
    csrf_token = register_and_login(client)
    category_id = client.get("/categories").json()[0]["id"]

    defaulted = client.post(
        "/expenses",
        json={"amount": "5.00", "category_id": category_id},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert defaulted.status_code == 201
    assert defaulted.json()["currency"] == "MYR"
    assert defaulted.json()["expense_date"] == date.today().isoformat()

    create_expense(
        client,
        csrf_token,
        amount="40.00",
        merchant="Cafe",
        expense_date="2026-11-11",
    )
    create_expense(
        client,
        csrf_token,
        amount="10.00",
        merchant="Taxi",
        expense_date="2026-11-12",
    )

    assert client.get("/expenses?search=Cafe").json()[0]["merchant"] == "Cafe"
    assert (
        client.get("/expenses?start_date=2026-11-12&end_date=2026-11-12").json()[0]["merchant"]
        == "Taxi"
    )
    assert client.get("/expenses?sort=amount_desc").json()[0]["amount"] == "40.00"


def test_does_not_accept_user_id_from_request(client: TestClient):
    csrf_token = register_and_login(client)
    response, _ = create_expense(
        client,
        csrf_token,
        user_id="00000000-0000-0000-0000-000000000001",
    )

    assert response.status_code == 422


def test_rejects_category_owned_by_another_user(client: TestClient):
    csrf_token = register_and_login(client, "alice")
    category_id = client.get("/categories").json()[0]["id"]
    response, _ = create_expense(client, csrf_token, category_id=category_id)
    assert response.status_code == 201

    other_client = TestClient(client.app)
    other_csrf = register_and_login(other_client, "bob")
    invalid, _ = create_expense(other_client, other_csrf, category_id=category_id)

    assert invalid.status_code == 422
    other_client.close()


def test_unauthorized_requests_are_rejected(client: TestClient):
    response = client.get("/expenses")
    create_response = client.post(
        "/expenses",
        json={
            "amount": "10",
            "category_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 401
    assert create_response.status_code == 401


def test_register_and_login_through_browser_forms(client: TestClient):
    registration_page = client.get("/register")
    registration_csrf = client.cookies.get("expense_pre_auth_csrf")
    assert registration_csrf in registration_page.text

    registered = client.post(
        "/auth/register",
        data={
            "username": "formuser",
            "email": "formuser@example.com",
            "password": "correct horse battery staple",
            "csrf_token": registration_csrf,
        },
        follow_redirects=False,
    )
    assert registered.status_code == 303

    login_page = client.get("/login")
    login_csrf = client.cookies.get("expense_pre_auth_csrf")
    assert login_csrf in login_page.text
    logged_in = client.post(
        "/auth/login",
        data={
            "username": "formuser",
            "password": "correct horse battery staple",
            "csrf_token": login_csrf,
        },
    )

    assert logged_in.status_code == 200
    assert "Add Expense" in logged_in.text


def test_user_cannot_retrieve_update_or_delete_another_users_expense(client: TestClient):
    alice_csrf = register_and_login(client, "alice")
    expense_response, _ = create_expense(client, alice_csrf)
    expense_id = expense_response.json()["id"]

    bob_client = TestClient(client.app)
    bob_csrf = register_and_login(bob_client, "bob")

    assert bob_client.get(f"/expenses/{expense_id}").status_code == 404
    assert (
        bob_client.put(
            f"/expenses/{expense_id}",
            json={
                "amount": "25.00",
                "currency": "MYR",
                "category_id": bob_client.get("/categories").json()[0]["id"],
                "expense_date": "2026-11-12",
            },
            headers={"X-CSRF-Token": bob_csrf},
        ).status_code
        == 404
    )
    assert (
        bob_client.delete(
            f"/expenses/{expense_id}",
            headers={"X-CSRF-Token": bob_csrf},
        ).status_code
        == 404
    )
    assert bob_client.get("/expenses").json() == []
    bob_client.close()


def test_owner_can_update_and_delete_expense(client: TestClient):
    csrf_token = register_and_login(client)
    created, _ = create_expense(client, csrf_token)
    expense_id = created.json()["id"]
    category_id = created.json()["category_id"]

    updated = client.put(
        f"/expenses/{expense_id}",
        json={
            "amount": "42.10",
            "currency": "usd",
            "category_id": category_id,
            "expense_date": "2026-11-10",
            "merchant": "Market",
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert updated.status_code == 200
    assert updated.json()["amount"] == "42.10"
    assert updated.json()["currency"] == "USD"
    assert updated.json()["merchant"] == "Market"
    assert (
        client.delete(
            f"/expenses/{expense_id}",
            headers={"X-CSRF-Token": csrf_token},
        ).status_code
        == 204
    )
    assert client.get(f"/expenses/{expense_id}").status_code == 404


def test_dashboard_and_quick_entry_form_render(client: TestClient):
    csrf_token = register_and_login(client)
    response = client.get("/")

    assert response.status_code == 200
    assert "Add Expense" in response.text
    assert "Categories" in response.text
    assert csrf_token in response.text
    form = client.get("/expenses/new")
    assert form.status_code == 200
    assert 'value="MYR"' in form.text
    assert date.today().isoformat() in form.text
    openapi = client.get("/openapi.json").json()
    assert "requestBody" in openapi["paths"]["/expenses"]["post"]


def test_dashboard_statistics_filter_dates_currencies_and_users(client: TestClient):
    csrf_token = register_and_login(client, "alice")
    today = date.today()
    create_expense(client, csrf_token, expense_date=today.isoformat(), amount="18.75")
    create_expense(
        client,
        csrf_token,
        expense_date=today.isoformat(),
        amount="10.00",
        currency="USD",
    )
    create_expense(
        client,
        csrf_token,
        expense_date=(today - timedelta(days=1)).isoformat(),
        amount="50.00",
    )

    other_client = TestClient(client.app)
    other_csrf = register_and_login(other_client, "bob")
    create_expense(other_client, other_csrf, expense_date=today.isoformat(), amount="99.00")

    response = client.get(f"/?start_date={today.isoformat()}&end_date={today.isoformat()}")

    assert response.status_code == 200
    assert 'id="dashboard-expense-count">2</div>' in response.text
    assert response.text.count("<polyline ") == 2
    totals = response.text.split('id="dashboard-total">', 1)[1].split(
        '<div class="col-12 col-md-4">', 1
    )[0]
    assert "MYR 18.75" in totals
    assert "USD 10.00" in totals
    assert "50.00" not in totals
    assert "99.00" not in totals
    other_client.close()


def test_dashboard_rejects_reversed_date_range(client: TestClient):
    register_and_login(client)

    response = client.get("/?start_date=2026-11-13&end_date=2026-11-12")

    assert response.status_code == 422


@pytest.mark.parametrize("days", [31, 731])
def test_dashboard_trend_handles_monthly_and_yearly_ranges(
    client: TestClient, days: int
):
    csrf_token = register_and_login(client)
    today = date.today()
    create_expense(client, csrf_token, expense_date=today.isoformat())

    response = client.get(
        f"/?start_date={(today - timedelta(days=days)).isoformat()}"
        f"&end_date={today.isoformat()}"
    )

    assert response.status_code == 200
    assert "Spending over time" in response.text


def test_dashboard_draws_a_trend_line_with_zero_spend_days(client: TestClient):
    csrf_token = register_and_login(client)
    today = date.today()
    create_expense(client, csrf_token, expense_date=today.isoformat(), amount="25.00")
    create_expense(
        client,
        csrf_token,
        expense_date=(today - timedelta(days=2)).isoformat(),
        amount="10.00",
    )

    response = client.get(
        f"/?start_date={(today - timedelta(days=2)).isoformat()}"
        f"&end_date={today.isoformat()}"
    )

    assert response.status_code == 200
    assert response.text.count("<circle ") == 3
    assert "<polyline " in response.text
    assert (today - timedelta(days=1)).strftime("%d %b") in response.text


def test_htmx_form_create_update_and_delete(client: TestClient):
    csrf_token = register_and_login(client)
    form_data = {
        "amount": "12.50",
        "category_id": client.get("/categories").json()[0]["id"],
        "expense_date": "2026-11-12",
        "csrf_token": csrf_token,
    }
    created = client.post(
        "/expenses/form",
        data=form_data,
        headers={"HX-Request": "true"},
    )

    assert created.status_code == 200
    assert "12.50" in created.text
    assert created.headers["HX-Trigger"] == "expenseSaved"
    expense_id = client.get("/expenses").json()[0]["id"]

    updated = client.post(
        f"/expenses/{expense_id}/edit",
        data={**form_data, "amount": "25.00"},
        headers={"HX-Request": "true"},
    )
    assert updated.status_code == 200
    assert "25.00" in updated.text

    deleted = client.post(
        f"/expenses/{expense_id}/delete",
        data={"csrf_token": csrf_token},
        headers={"HX-Request": "true"},
    )
    assert deleted.status_code == 200
    assert deleted.headers["HX-Trigger"] == "expenseSaved"
    assert "No expenses yet" in deleted.text


def test_form_validation_shows_an_error_and_logout_revokes_session(client: TestClient):
    csrf_token = register_and_login(client)
    invalid = client.post(
        "/expenses/form",
        data={
            "amount": "-1",
            "category_id": client.get("/categories").json()[0]["id"],
            "expense_date": "2026-11-12",
            "csrf_token": csrf_token,
        },
        headers={"HX-Request": "true"},
    )
    assert invalid.status_code == 200
    assert "greater than 0" in invalid.text

    logout = client.post(
        "/auth/logout",
        data={"csrf_token": csrf_token},
    )
    assert logout.status_code == 204
    assert client.get("/expenses").status_code == 401
