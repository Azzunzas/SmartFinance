from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import SESSION_COOKIE_NAME, get_session
from api.main import app
from core.models import AppUser


@pytest.fixture(autouse=True)
def _clean_app_user(db_session: Session) -> None:
    """Estes testes assumem `app_user` vazia (pra `/register` funcionar).
    Isso é verdade hoje, mas deixa de ser assim que o usuário real for
    registrado fora de teste — e como o resto do projeto, a transação de teste
    enxerga dado real já commitado (`tests/conftest.py`). Apagar aqui é
    seguro: é dentro da própria transação do teste, sempre revertida, não
    mexe no dado real."""
    db_session.execute(sa.delete(AppUser))
    db_session.flush()


@pytest.fixture
def auth_client(db_session: Session) -> Iterator[TestClient]:
    """Diferente do `client` de `conftest.py`: não sobrescreve `require_auth`
    — é o único jeito de testar o fluxo de login/sessão de verdade. Cada
    `TestClient` tem seu próprio cookie jar (httpx), então dois `auth_client`
    diferentes nunca compartilham sessão sem querer."""
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _register(
    client: TestClient, *, username: str = "guilherme", password: str = "senha-forte-123"
) -> None:
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 201, response.text


def test_register_creates_user_and_sets_session_cookie(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/auth/register", json={"username": "guilherme", "password": "senha-forte-123"}
    )
    assert response.status_code == 201
    assert response.json() == {"username": "guilherme"}
    assert SESSION_COOKIE_NAME in response.cookies


def test_register_fails_when_user_already_exists(auth_client: TestClient) -> None:
    _register(auth_client)

    response = auth_client.post(
        "/api/auth/register", json={"username": "outro", "password": "outra-senha-123"}
    )
    assert response.status_code == 409


def test_login_succeeds_with_correct_credentials(auth_client: TestClient) -> None:
    _register(auth_client)

    fresh_client = TestClient(app)
    response = fresh_client.post(
        "/api/auth/login", json={"username": "guilherme", "password": "senha-forte-123"}
    )
    assert response.status_code == 200
    assert response.json() == {"username": "guilherme"}
    assert SESSION_COOKIE_NAME in response.cookies


def test_login_fails_with_wrong_password(auth_client: TestClient) -> None:
    _register(auth_client)

    fresh_client = TestClient(app)
    response = fresh_client.post(
        "/api/auth/login", json={"username": "guilherme", "password": "senha-errada"}
    )
    assert response.status_code == 401


def test_login_fails_with_unknown_username(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/auth/login", json={"username": "nao-existe", "password": "qualquer-coisa"}
    )
    assert response.status_code == 401


def test_protected_endpoint_requires_auth(auth_client: TestClient) -> None:
    response = auth_client.get("/api/metrics/overview")
    assert response.status_code == 401


def test_protected_endpoint_works_after_login(auth_client: TestClient) -> None:
    _register(auth_client)

    response = auth_client.get("/api/metrics/overview")
    assert response.status_code == 200


def test_me_returns_username_when_authenticated(auth_client: TestClient) -> None:
    _register(auth_client)

    response = auth_client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"username": "guilherme"}


def test_me_requires_auth(auth_client: TestClient) -> None:
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout_revokes_session(auth_client: TestClient) -> None:
    _register(auth_client)
    assert auth_client.get("/api/auth/me").status_code == 200

    logout_response = auth_client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    # sessão apagada no servidor, não só cookie limpo no cliente — mesmo se
    # o cookie ainda fosse reenviado, a sessão não existiria mais.
    assert auth_client.get("/api/auth/me").status_code == 401


def test_logout_is_idempotent_without_session(auth_client: TestClient) -> None:
    response = auth_client.post("/api/auth/logout")
    assert response.status_code == 204
