"""Higiene de identificadores em texto livre que vai parar no banco e na tela.

docs/regras-do-projeto.md §3: "Mensagens de log sem dados financeiros identificáveis."

O caso concreto que motivou isto (2026-08-23): uma falha de sync gravava
`str(exc)` cru em `sync_run.error_message`, e a exceção da httpx carrega a URL
inteira — `.../items/9f3949f5-7012-4032-bdeb-f8c334bbd37a`. O `item_id` da
Pluggy não é credencial (sozinho não abre nada), mas é o identificador que liga
uma pessoa a uma conta bancária, e ele estava sendo devolvido pelo
`GET /api/sync/runs` em texto puro.

Redigir sem mais nada apagaria a única pista de QUAL conexão falhou, então a
migration 0015 passou a guardar `sync_run.connection_id` como FK de verdade.
Diagnóstico melhora e o identificador some do texto livre — não é troca.
"""

import re

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# A apiKey da Pluggy é um JWT. Ela é gerada em runtime e nunca persistida, mas
# se algum dia aparecer num corpo de resposta ecoado numa exceção, não pode
# chegar ao banco.
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")

ERROR_MESSAGE_LIMIT = 2000


def redact_identifiers(message: str, *, limit: int = ERROR_MESSAGE_LIMIT) -> str:
    """Troca UUIDs e JWTs por marcadores, preservando o resto da mensagem.

    O que sobra continua diagnóstico: "Client error '404 Not Found' for url
    'https://api.pluggy.ai/items/<id-omitido>'" diz o mesmo sobre o que
    aconteceu, sem dizer com quem.
    """
    redacted = _UUID_RE.sub("<id-omitido>", message)
    redacted = _JWT_RE.sub("<token-omitido>", redacted)
    return redacted[:limit]
