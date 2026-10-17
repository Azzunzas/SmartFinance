from core.redaction import redact_identifiers


def test_redacts_item_id_from_a_real_pluggy_error() -> None:
    """A mensagem exata que estava indo pro banco antes de 2026-08-23."""
    original = (
        "Client error '404 Not Found' for url "
        "'https://api.pluggy.ai/items/9f3949f5-7012-4032-bdeb-f8c334bbd37a'"
    )
    limpo = redact_identifiers(original)
    assert "9f3949f5" not in limpo
    # o diagnóstico sobrevive: continua dizendo O QUE houve, só não com quem
    assert "404 Not Found" in limpo
    assert "api.pluggy.ai/items/<id-omitido>" in limpo


def test_redacts_every_uuid_not_just_the_first() -> None:
    texto = (
        "conta 11111111-1111-1111-1111-111111111111 do item "
        "22222222-2222-2222-2222-222222222222"
    )
    assert redact_identifiers(texto).count("<id-omitido>") == 2


def test_redacts_a_jwt_shaped_token() -> None:
    """A apiKey da Pluggy é um JWT. Nunca é persistida, mas se aparecer num
    corpo de resposta ecoado numa exceção, não pode chegar ao banco."""
    texto = "falhou com apiKey eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk"
    limpo = redact_identifiers(texto)
    assert "eyJhbGciOiJIUzI1NiJ9" not in limpo
    assert "<token-omitido>" in limpo


def test_leaves_ordinary_messages_intact() -> None:
    assert redact_identifiers("timeout ao falar com a Pluggy") == "timeout ao falar com a Pluggy"


def test_respects_the_length_limit() -> None:
    assert len(redact_identifiers("x" * 5000)) == 2000
