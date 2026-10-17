import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class TransactionClassification(Base):
    """Regra de domínio 7, aplicada em dois níveis.

    O primeiro nível é esta tabela existir separada de `transaction`: o sync
    reescreve `transaction`, nunca toca aqui.

    O segundo nível (migration 0013) é a separação DENTRO da linha. Cada campo
    que o `run_analysis` calcula existe três vezes:

      `<campo>_auto`    o que o run_analysis achou — só ele escreve
      `<campo>_manual`  o que você decidiu — só você escreve; NULL = "não opinei"
      `<campo>`         COALESCE(manual, auto), calculado pelo Postgres

    Antes da 0013 os dois moravam na mesma coluna, com uma flag `source` por
    linha decidindo quem mandava. Isso significava que qualquer edição manual
    — inclusive escrever só uma nota — congelava a classificação automática de
    TODOS os campos daquela transação pra sempre. Ver a migration 0013 pro
    caso concreto que isso quebrava.

    `exclude_from_analysis` e `note` não entram na separação: o
    `upsert_auto_classification` nunca escreveu neles, já são seus por
    construção.
    """

    __tablename__ = "transaction_classification"

    transaction_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("transaction.id"), primary_key=True
    )

    # --- o que o run_analysis calculou -------------------------------------
    category_id_auto: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("category.id"))
    is_internal_transfer_auto: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    is_card_payment_auto: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    counterpart_tx_id_auto: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("transaction.id")
    )

    # --- o que você decidiu; None é "não opinei", diferente de "opinei False"
    category_id_manual: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("category.id")
    )
    is_internal_transfer_manual: Mapped[bool | None] = mapped_column(sa.Boolean)
    is_card_payment_manual: Mapped[bool | None] = mapped_column(sa.Boolean)
    counterpart_tx_id_manual: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("transaction.id")
    )

    # --- resolvidas pelo Postgres: SOMENTE LEITURA -------------------------
    # `sa.Computed` faz o SQLAlchemy excluir estas colunas de todo INSERT e
    # UPDATE automaticamente. Tentar atribuir valor a elas é erro do Postgres,
    # não bug silencioso. É o que permite que toda query de leitura do repo
    # continue usando o nome antigo sem saber que a implementação mudou.
    category_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.Computed("COALESCE(category_id_manual, category_id_auto)", persisted=True),
    )
    is_internal_transfer: Mapped[bool] = mapped_column(
        sa.Boolean,
        sa.Computed(
            "COALESCE(is_internal_transfer_manual, is_internal_transfer_auto)", persisted=True
        ),
    )
    is_card_payment: Mapped[bool] = mapped_column(
        sa.Boolean,
        sa.Computed("COALESCE(is_card_payment_manual, is_card_payment_auto)", persisted=True),
    )
    counterpart_tx_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.Computed(
            "COALESCE(counterpart_tx_id_manual, counterpart_tx_id_auto)", persisted=True
        ),
    )

    # --- seus, sem disputa --------------------------------------------------
    exclude_from_analysis: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    note: Mapped[str | None] = mapped_column(sa.Text)
    updated_at: Mapped[dt.datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
