from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import Category


def test_list_categories_returns_ordered_catalog(
    client: TestClient, db_session: Session
) -> None:
    category_z = Category(name="ZZ Teste", kind="EXPENSE")
    category_a = Category(name="AA Teste", kind="INCOME")
    db_session.add_all([category_z, category_a])
    db_session.flush()

    response = client.get("/api/categories")

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body]
    assert category_a.id in ids
    assert category_z.id in ids
    assert ids.index(category_a.id) < ids.index(category_z.id)
    assert next(item for item in body if item["id"] == category_a.id) == {
        "id": category_a.id,
        "parent_id": None,
        "name": "AA Teste",
        "kind": "INCOME",
    }
