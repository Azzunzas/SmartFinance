from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.ingestion.normalize import normalize_description
from core.models import Category
from core.models.classification import TransactionClassification
from core.models.transaction import Direction

from .conftest import make_transaction


def test_list_returns_transactions_ordered_by_date_desc(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    db_session.add(
        make_transaction(
            account_id,
            suffix="older",
            description="MAIS ANTIGA",
            amount="10.00",
            direction=Direction.OUT,
            day=1,
        )
    )
    db_session.add(
        make_transaction(
            account_id,
            suffix="newer",
            description="MAIS RECENTE",
            amount="20.00",
            direction=Direction.OUT,
            day=10,
        )
    )
    db_session.flush()

    response = client.get("/api/transactions", params={"account_id": account_id})
    assert response.status_code == 200
    dates = [item["date"] for item in response.json()["items"]]
    assert dates == sorted(dates, reverse=True)


def test_pagination_cursor_advances_and_ends(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    for day in (1, 2, 3):
        db_session.add(
            make_transaction(
                account_id,
                suffix=f"page-{day}",
                description="TESTE PAGINACAO",
                amount="5.00",
                direction=Direction.OUT,
                day=day,
            )
        )
    db_session.flush()

    first = client.get("/api/transactions", params={"limit": 2, "account_id": account_id})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second = client.get(
        "/api/transactions",
        params={"limit": 2, "account_id": account_id, "cursor": first_body["next_cursor"]},
    )
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None

    seen_ids = {item["id"] for item in first_body["items"] + second_body["items"]}
    assert len(seen_ids) == 3


def test_filter_by_direction(client: TestClient, db_session: Session, account_id: int) -> None:
    db_session.add(
        make_transaction(
            account_id,
            suffix="in",
            description="ENTRADA",
            amount="100.00",
            direction=Direction.IN,
            day=5,
        )
    )
    db_session.add(
        make_transaction(
            account_id,
            suffix="out",
            description="SAIDA",
            amount="100.00",
            direction=Direction.OUT,
            day=5,
        )
    )
    db_session.flush()

    response = client.get("/api/transactions", params={"direction": "IN", "account_id": account_id})
    directions = {item["direction"] for item in response.json()["items"]}
    assert directions == {"IN"}


def test_filter_by_category(client: TestClient, db_session: Session, account_id: int) -> None:
    category = Category(name="Filtro categoria", kind="EXPENSE")
    db_session.add(category)
    included = make_transaction(
        account_id,
        suffix="category-in",
        description="INCLUIDA",
        amount="10.00",
        direction=Direction.OUT,
        day=5,
    )
    excluded = make_transaction(
        account_id,
        suffix="category-out",
        description="EXCLUIDA",
        amount="10.00",
        direction=Direction.OUT,
        day=6,
    )
    db_session.add_all([included, excluded])
    db_session.flush()
    db_session.add(
        TransactionClassification(
            transaction_id=included.id,
            category_id_auto=category.id,
            is_internal_transfer_auto=False,
            is_card_payment_auto=False,
            exclude_from_analysis=False,
        )
    )
    db_session.flush()

    response = client.get(
        "/api/transactions",
        params={"account_id": account_id, "category_id": category.id},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [included.id]


def test_filter_sem_categoria_includes_null_classification(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    sem_categoria = Category(name="Sem categoria", kind="EXPENSE")
    transaction = make_transaction(
        account_id,
        suffix="unclassified",
        description="SEM CLASSIFICACAO",
        amount="10.00",
        direction=Direction.OUT,
        day=5,
    )
    db_session.add_all([sem_categoria, transaction])
    db_session.flush()

    response = client.get(
        "/api/transactions",
        params={"account_id": account_id, "category_id": sem_categoria.id},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [transaction.id]


def test_filter_by_payment_method(client: TestClient, db_session: Session, account_id: int) -> None:
    pix = make_transaction(
        account_id,
        suffix="pix",
        description="PIX RECEBIDO",
        amount="30.00",
        direction=Direction.IN,
        day=5,
    )
    pix.payment_method = "PIX"
    db_session.add(pix)
    db_session.add(
        make_transaction(
            account_id,
            suffix="nopix",
            description="COMPRA CARTAO",
            amount="30.00",
            direction=Direction.OUT,
            day=5,
        )
    )
    db_session.flush()

    response = client.get(
        "/api/transactions", params={"payment_method": "PIX", "account_id": account_id}
    )
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["payment_method"] == "PIX"


def test_filter_by_period_uses_accrual_date(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    august = make_transaction(
        account_id,
        suffix="august",
        description="AGOSTO",
        amount="10.00",
        direction=Direction.OUT,
        day=15,
    )
    september = make_transaction(
        account_id,
        suffix="september",
        description="SETEMBRO",
        amount="10.00",
        direction=Direction.OUT,
        day=15,
    )
    september.date = date(2026, 9, 15)
    september.accrual_date = date(2026, 9, 15)
    db_session.add(august)
    db_session.add(september)
    db_session.flush()

    response = client.get(
        "/api/transactions", params={"period": "2026-09", "account_id": account_id}
    )
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["accrual_date"] == "2026-09-15"


def test_search_normalizes_accents_and_case(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    tx = make_transaction(
        account_id,
        suffix="cafe",
        description="Café Padaria",
        amount="15.00",
        direction=Direction.OUT,
        day=5,
    )
    tx.description_norm = normalize_description(tx.description)
    db_session.add(tx)
    db_session.flush()

    response = client.get("/api/transactions", params={"search": "cafe", "account_id": account_id})
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["description"] == "Café Padaria"


def test_classification_fields_included_when_present(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    category = Category(name="Alimentação", kind="EXPENSE")
    db_session.add(category)
    db_session.flush()

    tx = make_transaction(
        account_id,
        suffix="classified",
        description="RESTAURANTE",
        amount="45.00",
        direction=Direction.OUT,
        day=5,
    )
    db_session.add(tx)
    db_session.flush()

    db_session.add(
        TransactionClassification(
            transaction_id=tx.id,
            category_id_auto=category.id,
            is_internal_transfer_auto=True,
            is_internal_transfer_manual=False,
            is_card_payment_auto=False,
            is_card_payment_manual=True,
            exclude_from_analysis=False,
        )
    )
    db_session.flush()

    response = client.get("/api/transactions", params={"account_id": account_id})
    item = next(i for i in response.json()["items"] if i["id"] == tx.id)
    assert item["category_name"] == "Alimentação"
    assert item["category_id_auto"] == category.id
    assert item["category_id_manual"] is None
    assert item["is_internal_transfer"] is False
    assert item["is_internal_transfer_auto"] is True
    assert item["is_internal_transfer_manual"] is False
    assert item["is_card_payment"] is True
    assert item["is_card_payment_auto"] is False
    assert item["is_card_payment_manual"] is True


def test_invalid_cursor_returns_422(client: TestClient) -> None:
    response = client.get("/api/transactions", params={"cursor": "not-a-valid-cursor!!!"})
    assert response.status_code == 422


def test_invalid_period_format_returns_422(client: TestClient) -> None:
    response = client.get("/api/transactions", params={"period": "2026/09"})
    assert response.status_code == 422


def test_patch_classification_creates_manual_record(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    tx = make_transaction(
        account_id,
        suffix="patch-new",
        description="COMPRA X",
        amount="20.00",
        direction=Direction.OUT,
        day=5,
    )
    db_session.add(tx)
    db_session.flush()

    response = client.patch(
        f"/api/transactions/{tx.id}/classification",
        json={"exclude_from_analysis": True, "note": "revisão manual"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exclude_from_analysis"] is True
    assert body["note"] == "revisão manual"
    # campo não enviado no PATCH não devia ganhar um valor arbitrário
    assert body["is_internal_transfer"] is False


def test_patch_classification_overrides_previous_manual_decision(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    tx = make_transaction(
        account_id,
        suffix="patch-twice",
        description="COMPRA Y",
        amount="20.00",
        direction=Direction.OUT,
        day=5,
    )
    db_session.add(tx)
    db_session.flush()

    client.patch(f"/api/transactions/{tx.id}/classification", json={"is_card_payment": True})
    second = client.patch(
        f"/api/transactions/{tx.id}/classification", json={"is_card_payment": False}
    )
    assert second.json()["is_card_payment"] is False


def test_patch_classification_can_return_field_to_automatic(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    tx = make_transaction(
        account_id,
        suffix="reset-manual",
        description="TRANSFERENCIA",
        amount="20.00",
        direction=Direction.OUT,
        day=5,
    )
    db_session.add(tx)
    db_session.flush()
    db_session.add(
        TransactionClassification(
            transaction_id=tx.id,
            is_internal_transfer_auto=True,
            is_internal_transfer_manual=False,
            is_card_payment_auto=False,
            exclude_from_analysis=False,
        )
    )
    db_session.flush()

    response = client.patch(
        f"/api/transactions/{tx.id}/classification",
        json={"reset_fields": ["is_internal_transfer"]},
    )

    assert response.status_code == 200
    assert response.json()["is_internal_transfer"] is True
    classification = db_session.get(TransactionClassification, tx.id)
    assert classification is not None
    db_session.refresh(classification)
    assert classification.is_internal_transfer_manual is None


def test_patch_classification_missing_transaction_returns_404(client: TestClient) -> None:
    response = client.patch("/api/transactions/999999999/classification", json={"note": "x"})
    assert response.status_code == 404


def test_bulk_classify_reports_updated_and_missing_ids(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    tx_a = make_transaction(
        account_id,
        suffix="bulk-a",
        description="ITEM A",
        amount="10.00",
        direction=Direction.OUT,
        day=5,
    )
    tx_b = make_transaction(
        account_id,
        suffix="bulk-b",
        description="ITEM B",
        amount="10.00",
        direction=Direction.OUT,
        day=6,
    )
    db_session.add(tx_a)
    db_session.add(tx_b)
    db_session.flush()

    response = client.post(
        "/api/transactions/bulk-classify",
        json={
            "transaction_ids": [tx_a.id, tx_b.id, 999999999],
            "is_internal_transfer": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["updated_ids"]) == sorted([tx_a.id, tx_b.id])
    assert body["missing_ids"] == [999999999]

    check = client.get("/api/transactions", params={"account_id": account_id})
    updated = {item["id"]: item for item in check.json()["items"]}
    assert updated[tx_a.id]["is_internal_transfer"] is True
    assert updated[tx_b.id]["is_internal_transfer"] is True

    reset = client.post(
        "/api/transactions/bulk-classify",
        json={
            "transaction_ids": [tx_a.id, tx_b.id],
            "reset_fields": ["is_internal_transfer"],
        },
    )
    assert reset.status_code == 200
    check = client.get("/api/transactions", params={"account_id": account_id})
    reset_items = {item["id"]: item for item in check.json()["items"]}
    assert reset_items[tx_a.id]["is_internal_transfer"] is False
    assert reset_items[tx_b.id]["is_internal_transfer"] is False


def test_patch_rejects_value_and_reset_of_the_same_field(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    """Mandar valor e pedir reset do mesmo campo é contraditório. Antes o
    repositório escolhia o reset e descartava o valor em silêncio."""
    tx = make_transaction(
        account_id, suffix="conflito", description="X", amount="10.00",
        direction=Direction.OUT, day=5,
    )
    db_session.add(tx)
    db_session.flush()

    response = client.patch(
        f"/api/transactions/{tx.id}/classification",
        json={"category_id": 5, "reset_fields": ["category_id"]},
    )
    assert response.status_code == 422
    assert "reset do mesmo campo" in response.text


def test_patch_allows_reset_of_one_field_while_setting_another(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    """A guarda tem que pegar só o conflito real — resetar um campo e setar
    outro no mesmo corpo continua válido."""
    tx = make_transaction(
        account_id, suffix="sem-conflito", description="Y", amount="10.00",
        direction=Direction.OUT, day=5,
    )
    db_session.add(tx)
    db_session.flush()

    response = client.patch(
        f"/api/transactions/{tx.id}/classification",
        json={"is_card_payment": True, "reset_fields": ["category_id"]},
    )
    assert response.status_code == 200
    assert response.json()["is_card_payment"] is True


def test_bulk_classify_rejects_value_and_reset_of_the_same_field(
    client: TestClient, db_session: Session, account_id: int
) -> None:
    tx = make_transaction(
        account_id, suffix="conflito-lote", description="Z", amount="10.00",
        direction=Direction.OUT, day=5,
    )
    db_session.add(tx)
    db_session.flush()

    response = client.post(
        "/api/transactions/bulk-classify",
        json={
            "transaction_ids": [tx.id],
            "is_internal_transfer": True,
            "reset_fields": ["is_internal_transfer"],
        },
    )
    assert response.status_code == 422
