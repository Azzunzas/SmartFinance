from core.ingestion.normalize import (
    compute_account_fingerprint,
    compute_transaction_fingerprint,
    mask_account_number,
    normalize_description,
    resolve_accrual_date,
    resolve_direction,
)
from core.models.transaction import TxStatus
from core.repository.accounts import AccountUpsert
from core.repository.connections import ConnectionUpsert
from core.repository.investments import InvestmentUpsert
from core.repository.transactions import TransactionUpsert
from jobs.pluggy.schemas import PluggyAccount, PluggyInvestment, PluggyItem, PluggyTransaction

_INVESTMENT_ACTIVE_STATUS = "ACTIVE"

# Ponte entre a camada bruta (jobs/pluggy/schemas.py, espelha o JSON da Pluggy)
# e o domínio normalizado (core/). É por isso que esse arquivo mora em jobs/ e
# não em core/: core/ não pode depender de jobs/pluggy (regra do doc §6.1).


def map_connection(item: PluggyItem) -> ConnectionUpsert:
    return ConnectionUpsert(
        pluggy_item_id=item.id,
        connector_id=item.connector.id,
        connector_name=item.connector.name,
        status=item.status,
        execution_status=item.execution_status,
        last_updated_at=item.last_updated_at,
        consent_expires_at=item.consent_expires_at,
        raw=item.model_dump(mode="json", by_alias=True),
    )


def map_account(
    account: PluggyAccount, *, connection_id: int, connector_id: int
) -> AccountUpsert:
    number_masked = mask_account_number(account.number)
    fingerprint = compute_account_fingerprint(connector_id, account.subtype, number_masked)
    credit_data = account.credit_data
    return AccountUpsert(
        connection_id=connection_id,
        pluggy_account_id=account.id,
        fingerprint=fingerprint,
        type=account.type,
        subtype=account.subtype,
        name=account.name,
        number_masked=number_masked,
        currency_code=account.currency_code,
        balance=account.balance,
        credit_limit=credit_data.credit_limit if credit_data else None,
        available_credit_limit=credit_data.available_credit_limit if credit_data else None,
        brand=credit_data.brand if credit_data else None,
        balance_due_date=(
            credit_data.balance_due_date.date()
            if credit_data and credit_data.balance_due_date
            else None
        ),
        balance_close_date=(
            credit_data.balance_close_date.date()
            if credit_data and credit_data.balance_close_date
            else None
        ),
        minimum_payment=credit_data.minimum_payment if credit_data else None,
        raw=account.model_dump(mode="json", by_alias=True),
    )


def map_transaction(
    transaction: PluggyTransaction,
    *,
    account_id: int,
    account_type: str,
    account_fingerprint: str,
) -> TransactionUpsert:
    description_norm = normalize_description(transaction.description)
    direction = resolve_direction(account_type, transaction.amount)
    amount_abs = abs(transaction.amount)
    posted_date = transaction.date.date()

    metadata = transaction.credit_card_metadata
    installment_number = metadata.installment_number if metadata else None
    installment_total = metadata.total_installments if metadata else None
    accrual_date = resolve_accrual_date(posted_date, installment_number, installment_total)

    fingerprint = compute_transaction_fingerprint(
        account_fingerprint, transaction.date, amount_abs, direction, description_norm
    )
    status = TxStatus(transaction.status) if transaction.status else TxStatus.POSTED
    payment_method = transaction.payment_data.payment_method if transaction.payment_data else None

    return TransactionUpsert(
        account_id=account_id,
        pluggy_transaction_id=transaction.id,
        fingerprint=fingerprint,
        description=transaction.description,
        description_norm=description_norm,
        merchant_name=transaction.merchant.name if transaction.merchant else None,
        amount=transaction.amount,
        amount_abs=amount_abs,
        direction=direction,
        currency_code=transaction.currency_code,
        date=posted_date,
        occurred_at=transaction.date,
        accrual_date=accrual_date,
        status=status,
        installment_number=installment_number,
        installment_total=installment_total,
        pluggy_category=transaction.category,
        payment_method=payment_method,
        balance_after=transaction.balance,
        raw=transaction.model_dump(mode="json", by_alias=True),
    )


def map_investment(investment: PluggyInvestment, *, connection_id: int) -> InvestmentUpsert:
    """`is_active` normalizado uma vez aqui (doc regra #9) a partir do
    `status` real da Pluggy (`ACTIVE | PENDING | TOTAL_WITHDRAWAL`) — só
    `ACTIVE` conta como ativo; `PENDING` entra junto com `TOTAL_WITHDRAWAL`
    do lado de fora do filtro padrão da carteira."""
    return InvestmentUpsert(
        connection_id=connection_id,
        pluggy_investment_id=investment.id,
        name=investment.name,
        type=investment.type,
        subtype=investment.subtype,
        issuer=investment.issuer,
        status=investment.status,
        is_active=investment.status == _INVESTMENT_ACTIVE_STATUS,
        raw=investment.model_dump(mode="json", by_alias=True),
    )
