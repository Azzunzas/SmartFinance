import secrets
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.models import AppSession, AppUser

SESSION_DURATION = timedelta(days=7)


def has_user(session: Session) -> bool:
    return session.execute(sa.select(sa.func.count()).select_from(AppUser)).scalar_one() > 0


def create_user(session: Session, *, username: str, password_hash: str) -> AppUser:
    user = AppUser(username=username, password_hash=password_hash)
    session.add(user)
    session.flush()
    return user


def load_user_by_username(session: Session, username: str) -> AppUser | None:
    return session.execute(
        sa.select(AppUser).where(AppUser.username == username)
    ).scalar_one_or_none()


def create_session(session: Session, *, user_id: int, now: datetime) -> AppSession:
    """`id` é o próprio token opaco que vira valor do cookie —
    `secrets.token_urlsafe` usa `os.urandom` por baixo, adequado pra
    segredo (diferente de `uuid.uuid4`, que não é feito pra ser
    imprevisível)."""
    app_session = AppSession(
        id=secrets.token_urlsafe(32),
        user_id=user_id,
        expires_at=now + SESSION_DURATION,
    )
    session.add(app_session)
    session.flush()
    return app_session


def load_valid_session(session: Session, session_id: str, *, now: datetime) -> AppSession | None:
    return session.execute(
        sa.select(AppSession).where(AppSession.id == session_id, AppSession.expires_at > now)
    ).scalar_one_or_none()


def delete_session(session: Session, session_id: str) -> None:
    session.execute(sa.delete(AppSession).where(AppSession.id == session_id))
