from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from api.deps import COOKIE_SECURE, SESSION_COOKIE_NAME, get_session, require_auth
from api.schemas.auth import LoginRequest, MeOut, RegisterRequest
from core.auth.passwords import hash_password, verify_password, waste_time_like_a_real_check
from core.models import AppSession, AppUser
from core.repository.auth import (
    SESSION_DURATION,
    create_session,
    create_user,
    delete_session,
    has_user,
    load_user_by_username,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        max_age=int(SESSION_DURATION.total_seconds()),
    )


@router.post("/register", response_model=MeOut, status_code=201)
def register(
    body: RegisterRequest, response: Response, session: Session = Depends(get_session)
) -> MeOut:
    """Só funciona enquanto `app_user` estiver vazia — usuário único (doc
    arquitetura §6.4). Depois da primeira conta criada, sempre 409. Já loga
    (seta o cookie) na resposta, pra fechar o fluxo de "tela de cadastro"
    numa request só."""
    if has_user(session):
        raise HTTPException(status_code=409, detail="usuário já cadastrado")
    user = create_user(
        session, username=body.username, password_hash=hash_password(body.password)
    )
    app_session = create_session(session, user_id=user.id, now=datetime.now(UTC))
    _set_session_cookie(response, app_session.id)
    return MeOut(username=user.username)


@router.post("/login", response_model=MeOut)
def login(
    body: LoginRequest, response: Response, session: Session = Depends(get_session)
) -> MeOut:
    user = load_user_by_username(session, body.username)
    if user is None:
        waste_time_like_a_real_check()
        raise HTTPException(status_code=401, detail="usuário ou senha inválidos")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="usuário ou senha inválidos")

    app_session = create_session(session, user_id=user.id, now=datetime.now(UTC))
    _set_session_cookie(response, app_session.id)
    return MeOut(username=user.username)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session: Session = Depends(get_session),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> None:
    """Idempotente de propósito — sem `require_auth`: deslogar quando a
    sessão já expirou não deveria dar erro, o objetivo (não estar mais
    logado) já está cumprido."""
    if session_id is not None:
        delete_session(session, session_id)
    response.delete_cookie(key=SESSION_COOKIE_NAME)


@router.get("/me", response_model=MeOut)
def me(
    session: Session = Depends(get_session),
    current: AppSession = Depends(require_auth),
) -> MeOut:
    user = session.get_one(AppUser, current.user_id)
    return MeOut(username=user.username)
