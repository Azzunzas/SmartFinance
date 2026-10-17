import os
from collections.abc import Generator
from datetime import UTC, datetime

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import create_session
from core.models import AppSession
from core.repository.auth import load_valid_session

SESSION_COOKIE_NAME = "smartfinance_session"
# Secure=True (padrão) exige HTTPS pro navegador aceitar enviar o cookie de
# volta — em dev local (http://localhost) precisa ser False, senão login
# "funciona" mas nenhuma request seguinte carrega o cookie. Ver .env.example.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"


def get_session() -> Generator[Session]:
    """Uma transação por request: commit se o handler terminar sem exceção,
    rollback caso contrário (inclusive `HTTPException`, que também passa por
    aqui). Sem isso, todo POST/PATCH/DELETE executaria e pareceria funcionar
    — mas nada seria persistido de fato."""
    session = create_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_auth(
    session: Session = Depends(get_session),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AppSession:
    """Protege um router inteiro via `app.include_router(..., dependencies=
    [Depends(require_auth)])` (ver api/main.py) — explícito ali, não
    escondido em middleware. `Depends(get_session)` aqui é a mesma instância
    de sessão que o handler da rota recebe (FastAPI cacheia por request),
    então isso não abre uma segunda transação."""
    if session_id is None:
        raise HTTPException(status_code=401, detail="não autenticado")
    app_session = load_valid_session(session, session_id, now=datetime.now(UTC))
    if app_session is None:
        raise HTTPException(status_code=401, detail="sessão inválida ou expirada")
    return app_session
