from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

# Hash de referência computado uma vez, na importação do módulo — usado só
# pra gastar um tempo comparável ao de uma verificação real quando o
# usuário não existe (ver verify_password em api/routers/auth.py). Sem
# isso, "usuário não existe" responde mais rápido que "senha errada",
# o que vaza se um username está cadastrado só pelo tempo de resposta.
_DUMMY_HASH = _hasher.hash("senha-de-referencia-pra-tempo-constante")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def waste_time_like_a_real_check() -> None:
    """Chamar quando o usuário não existe, antes de responder 401 — gasta um
    tempo comparável ao de `verify_password` de verdade, pra "usuário não
    existe" não responder mais rápido que "senha errada" (vazamento por
    tempo de resposta revelando quais usernames estão cadastrados)."""
    verify_password("senha-qualquer", _DUMMY_HASH)
