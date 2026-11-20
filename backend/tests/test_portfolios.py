import pytest

from app.core import security
from app.core.config import settings
from app.services.auth import upsert_user


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret-123")


@pytest.fixture()
def alice(db):
    u = upsert_user(db, "google", "alice", "alice@example.com")
    return {"Authorization": f"Bearer {security.create_access_token(u.id)}"}


@pytest.fixture()
def bob(db):
    u = upsert_user(db, "google", "bob", "bob@example.com")
    return {"Authorization": f"Bearer {security.create_access_token(u.id)}"}


def _make(client, headers, name="Main"):
    r = client.post("/portfolios", json={"name": name}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def test_crud_flow(client, alice):
    pid = _make(client, alice)
    h = client.post(
        f"/portfolios/{pid}/holdings",
        json={"ticker": "aapl", "quantity": 10, "avg_price": 150.5},
        headers=alice,
    )
    assert h.status_code == 201 and h.json()["ticker"] == "AAPL"
    hid = h.json()["id"]

    u = client.put(
        f"/portfolios/{pid}/holdings/{hid}", json={"quantity": 12, "avg_price": 151}, headers=alice
    )
    assert u.json()["quantity"] == 12

    got = client.get(f"/portfolios/{pid}", headers=alice).json()
    assert got["holdings"][0]["avg_price"] == 151

    assert (
        client.put(f"/portfolios/{pid}", json={"name": "Renamed"}, headers=alice).json()["name"] == "Renamed"
    )
    assert client.delete(f"/portfolios/{pid}/holdings/{hid}", headers=alice).status_code == 204
    assert client.get(f"/portfolios/{pid}", headers=alice).json()["holdings"] == []
    assert client.delete(f"/portfolios/{pid}", headers=alice).status_code == 204
    assert client.get("/portfolios", headers=alice).json() == []


def test_users_cannot_see_or_touch_each_others_data(client, alice, bob):
    pid = _make(client, alice)
    hid = client.post(
        f"/portfolios/{pid}/holdings", json={"ticker": "MSFT", "quantity": 1, "avg_price": 1}, headers=alice
    ).json()["id"]

    assert client.get("/portfolios", headers=bob).json() == []
    body = {"ticker": "AAPL", "quantity": 1, "avg_price": 1}
    attempts = [
        client.get(f"/portfolios/{pid}", headers=bob),
        client.put(f"/portfolios/{pid}", json={"name": "x"}, headers=bob),
        client.delete(f"/portfolios/{pid}", headers=bob),
        client.post(f"/portfolios/{pid}/holdings", json=body, headers=bob),
        client.put(f"/portfolios/{pid}/holdings/{hid}", json={"quantity": 99, "avg_price": 1}, headers=bob),
        client.delete(f"/portfolios/{pid}/holdings/{hid}", headers=bob),
    ]
    assert [r.status_code for r in attempts] == [404] * 6

    mine = client.get(f"/portfolios/{pid}", headers=alice).json()
    assert mine["name"] == "Main" and mine["holdings"][0]["quantity"] == 1


def test_holding_id_from_another_portfolio_is_not_reachable(client, alice):
    p1, p2 = _make(client, alice, "A"), _make(client, alice, "B")
    hid = client.post(
        f"/portfolios/{p1}/holdings", json={"ticker": "KO", "quantity": 1, "avg_price": 1}, headers=alice
    ).json()["id"]
    r = client.put(f"/portfolios/{p2}/holdings/{hid}", json={"quantity": 5, "avg_price": 1}, headers=alice)
    assert r.status_code == 404


@pytest.mark.parametrize(
    "body,status",
    [
        ({"ticker": "ZZZZ", "quantity": 1, "avg_price": 1}, 422),  # not in universe
        ({"ticker": "AAPL", "quantity": 0, "avg_price": 1}, 422),
        ({"ticker": "AAPL", "quantity": -3, "avg_price": 1}, 422),
        ({"ticker": "AAPL", "quantity": 1, "avg_price": -1}, 422),
        ({"ticker": "AAPL", "quantity": 1e12, "avg_price": 1}, 422),
        ({"ticker": "AAPL", "quantity": "abc", "avg_price": 1}, 422),
        ({"ticker": "AAPL", "quantity": 1}, 422),
    ],
)
def test_holding_validation(client, alice, body, status):
    pid = _make(client, alice)
    assert client.post(f"/portfolios/{pid}/holdings", json=body, headers=alice).status_code == status


def test_duplicate_ticker_conflicts(client, alice):
    pid = _make(client, alice)
    body = {"ticker": "AAPL", "quantity": 1, "avg_price": 1}
    assert client.post(f"/portfolios/{pid}/holdings", json=body, headers=alice).status_code == 201
    assert client.post(f"/portfolios/{pid}/holdings", json=body, headers=alice).status_code == 409


def test_blank_portfolio_name_rejected(client, alice):
    assert client.post("/portfolios", json={"name": "   "}, headers=alice).status_code == 422
    assert client.post("/portfolios", json={"name": "x" * 101}, headers=alice).status_code == 422


def test_limits(client, alice, monkeypatch):
    monkeypatch.setattr(settings, "max_portfolios", 2)
    monkeypatch.setattr(settings, "max_holdings", 1)
    pid = _make(client, alice, "1")
    _make(client, alice, "2")
    assert client.post("/portfolios", json={"name": "3"}, headers=alice).status_code == 409
    client.post(
        f"/portfolios/{pid}/holdings", json={"ticker": "AAPL", "quantity": 1, "avg_price": 1}, headers=alice
    )
    r = client.post(
        f"/portfolios/{pid}/holdings", json={"ticker": "MSFT", "quantity": 1, "avg_price": 1}, headers=alice
    )
    assert r.status_code == 409


def test_deleting_portfolio_removes_its_holdings(client, db, alice):
    from app.models import Holding

    pid = _make(client, alice)
    client.post(
        f"/portfolios/{pid}/holdings", json={"ticker": "AAPL", "quantity": 1, "avg_price": 1}, headers=alice
    )
    client.delete(f"/portfolios/{pid}", headers=alice)
    assert db.query(Holding).count() == 0
