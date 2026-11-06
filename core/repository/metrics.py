import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.analysis.health import (
    BURN_RATE_MONTHS,
    NET_WORTH_TREND_DAYS,
    HealthInputs,
    MonthlyTotals,
)
from core.analysis.planned_matching import PlannedKind
from core.models import Account, Category, PlannedItem, PlannedItemMatch, TransactionClassification
from core.models.transaction import Direction, Transaction, TxStatus
from core.repository.investments import list_investments


@dataclass(frozen=True, slots=True)
class AccountBalance:
    account_id: int
    name: str | None
    type: str
    subtype: str | None
    # Anulável porque `account.balance` é anulável (migration 0001) — a Pluggy
    # pode não devolver saldo pra uma conta. Expor None em vez de fingir R$ 0
    # segue o mesmo raciocínio de `resolve_category`: mostrar o buraco.
    balance: Decimal | None


@dataclass(frozen=True, slots=True)
class OverviewRecord:
    accounts: list[AccountBalance]
    open_credit_card_bill: Decimal
    investments_balance: Decimal
    net_worth: Decimal


def _total(accounts: list[AccountBalance], account_type: str) -> Decimal:
    return sum(
        (a.balance for a in accounts if a.type == account_type and a.balance is not None),
        Decimal(0),
    )


def load_overview(session: Session) -> OverviewRecord:
    """Patrimônio líquido = contas BANK + investimentos ativos − fatura em
    aberto (doc §5). Confirmado contra dado real que `account.balance` em
    conta CREDIT já é a fatura em aberto, positiva (bate com
    `credit_limit - available_credit_limit`) — por isso soma direto, sem
    inverter sinal."""
    rows = session.execute(
        sa.select(Account.id, Account.name, Account.type, Account.subtype, Account.balance)
        .where(Account.is_own, Account.include_in_analysis)
        .order_by(Account.type, Account.name)
    ).all()

    accounts = [
        AccountBalance(
            account_id=row.id,
            name=row.name,
            type=row.type,
            subtype=row.subtype,
            balance=row.balance,
        )
        for row in rows
    ]

    # `a.balance is not None` não é defensivismo: sem isso, uma única conta sem
    # saldo derruba o endpoint inteiro com TypeError (Decimal + None). Conta sem
    # saldo conhecido contribui zero pro total, mas continua aparecendo na lista
    # com balance=None, pra diferença ficar visível na tela.
    bank_total = _total(accounts, "BANK")
    credit_total = _total(accounts, "CREDIT")

    investments = list_investments(session, active_only=True)
    investments_total = sum((i.balance for i in investments if i.balance is not None), Decimal(0))

    return OverviewRecord(
        accounts=accounts,
        open_credit_card_bill=credit_total,
        investments_balance=investments_total,
        net_worth=bank_total + investments_total - credit_total,
    )


@dataclass(frozen=True, slots=True)
class PlannedVsActualRecord:
    planned_item_id: int
    name: str
    kind: str
    category_id: int | None
    expected_amount: Decimal
    tolerance_pct: Decimal
    matched_amount: Decimal


def load_planned_vs_actual(session: Session, period: str) -> list[PlannedVsActualRecord]:
    """Pra cada `planned_item` vigente no período (mesma regra "vigente hoje"
    que `budget-list.component.ts` já aplica no front, só que parametrizada
    pelo período em vez de sempre hoje), soma o `matched_amount` que
    `run_analysis` gravou. LEFT JOIN + COALESCE pra incluir item com **zero**
    match — some da lista seria pior que mostrar R$ 0."""
    rows = session.execute(
        sa.select(
            PlannedItem.id,
            PlannedItem.name,
            PlannedItem.kind,
            PlannedItem.category_id,
            PlannedItem.expected_amount,
            PlannedItem.tolerance_pct,
            sa.func.coalesce(sa.func.sum(PlannedItemMatch.matched_amount), 0).label("matched"),
        )
        .outerjoin(
            PlannedItemMatch,
            sa.and_(
                PlannedItemMatch.planned_item_id == PlannedItem.id,
                PlannedItemMatch.period == period,
            ),
        )
        .where(
            PlannedItem.is_active,
            sa.func.to_char(PlannedItem.valid_from, "YYYY-MM") <= period,
            sa.or_(
                PlannedItem.valid_to.is_(None),
                sa.func.to_char(PlannedItem.valid_to, "YYYY-MM") >= period,
            ),
        )
        .group_by(PlannedItem.id)
        .order_by(PlannedItem.kind, PlannedItem.name)
    ).all()
    return [
        PlannedVsActualRecord(
            planned_item_id=row.id,
            name=row.name,
            kind=row.kind,
            category_id=row.category_id,
            expected_amount=row.expected_amount,
            tolerance_pct=row.tolerance_pct,
            matched_amount=row.matched,
        )
        for row in rows
    ]


@dataclass(frozen=True, slots=True)
class MonthlyCashflowRecord:
    period: str
    total_in: Decimal
    total_out: Decimal
    net: Decimal


def load_monthly_cashflow(
    session: Session, *, reference_date: date, months: int, order: Literal["asc", "desc"]
) -> list[MonthlyCashflowRecord]:
    """Lê `mv_monthly_cashflow` (view já materializada e mantida atualizada
    por `run_analysis` via `REFRESH MATERIALIZED VIEW` — ver
    `core/repository/analysis.py::refresh_monthly_cashflow`). Este
    repositório só lê e agrega, não recalcula nada na hora da request
    (mesmo raciocínio de `load_planned_vs_actual`).

    Monta a lista dos últimos `months` períodos terminando em
    `reference_date` (ascendente por construção) e faz LEFT JOIN contra a
    view: período sem linha vira zero-fill (decisão de 2026-08-20 — não
    pular o mês, pro gráfico não ter buraco). `order="desc"` só inverte a
    lista já montada. `reference_date` é parâmetro explícito (não
    `date.today()` interno) pelo mesmo motivo de `project_upcoming`:
    quem chama decide "hoje", o que também torna a função testável sem
    mockar relógio."""
    periods = _past_periods(reference_date, months)

    rows = session.execute(
        sa.text(
            "SELECT period, total_in, total_out, net FROM mv_monthly_cashflow "
            "WHERE period IN :periods"
        ).bindparams(sa.bindparam("periods", expanding=True)),
        {"periods": periods},
    ).all()
    by_period = {row.period: row for row in rows}

    records = [
        MonthlyCashflowRecord(
            period=period,
            total_in=by_period[period].total_in if period in by_period else Decimal(0),
            total_out=by_period[period].total_out if period in by_period else Decimal(0),
            net=by_period[period].net if period in by_period else Decimal(0),
        )
        for period in periods
    ]

    if order == "desc":
        records.reverse()
    return records


def _past_periods(reference: date, months: int) -> list[str]:
    """Últimos `months` períodos (`YYYY-MM`) terminando no mês de
    `reference` (inclusive), do mais antigo pro mais recente."""
    return [_period(_add_months(reference, -offset)) for offset in range(months - 1, -1, -1)]


def _period(value: date) -> str:
    return value.strftime("%Y-%m")


def _add_months(reference: date, months: int) -> date:
    month_index = reference.month - 1 + months
    year = reference.year + month_index // 12
    month = month_index % 12 + 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True, slots=True)
class NetWorthPoint:
    date: date
    net_worth: Decimal


_NET_WORTH_SQL = """
WITH calendar AS (
    SELECT generate_series(:start_date, :end_date, interval '1 day')::date AS day
),
bank_credit AS (
    SELECT
        c.day,
        SUM(COALESCE(bs.balance, 0)) FILTER (WHERE a.type = 'BANK')   AS bank_total,
        SUM(COALESCE(bs.balance, 0)) FILTER (WHERE a.type = 'CREDIT') AS credit_total
    FROM calendar c
    CROSS JOIN account a
    LEFT JOIN LATERAL (
        SELECT balance FROM balance_snapshot
        WHERE account_id = a.id AND captured_at::date <= c.day
        ORDER BY captured_at DESC
        LIMIT 1
    ) bs ON true
    WHERE a.is_own AND a.include_in_analysis
    GROUP BY c.day
),
investments AS (
    SELECT
        c.day,
        SUM(COALESCE(isn.balance, 0)) AS investments_total
    FROM calendar c
    CROSS JOIN investment i
    LEFT JOIN LATERAL (
        SELECT balance FROM investment_snapshot
        WHERE investment_id = i.id AND captured_at::date <= c.day
        ORDER BY captured_at DESC
        LIMIT 1
    ) isn ON true
    WHERE i.is_active
    GROUP BY c.day
)
SELECT
    c.day,
    COALESCE(bc.bank_total, 0) + COALESCE(inv.investments_total, 0)
        - COALESCE(bc.credit_total, 0) AS net_worth
FROM calendar c
LEFT JOIN bank_credit bc ON bc.day = c.day
LEFT JOIN investments inv ON inv.day = c.day
ORDER BY c.day
"""


def load_net_worth_history(
    session: Session, *, reference_date: date, days: int
) -> list[NetWorthPoint]:
    """Patrimônio líquido por dia, últimos `days` dias terminando em
    `reference_date` (mesmo raciocínio de `reference_date` explícito de
    `load_monthly_cashflow`, pra ser testável sem mockar relógio).

    `balance_snapshot`/`investment_snapshot` são capturados a cada sync, em
    horários diferentes por conta — não tem uma linha por dia por conta.
    Por isso o `LEFT JOIN LATERAL ... captured_at::date <= c.day ORDER BY
    captured_at DESC LIMIT 1`: pra cada dia e cada conta/investimento, pega
    o snapshot mais recente até aquele dia (forward-fill / "último valor
    conhecido"), não o snapshot exatamente daquele dia.

    Isso é diferente do zero-fill do cashflow de propósito: lá, mês sem
    transação é zero de verdade (não gastou). Aqui, dia sem snapshot **não**
    é saldo zero — é só "não sincronizou esse dia", o saldo real continua
    sendo o último capturado. `COALESCE(balance, 0)` só vira zero de fato
    antes do *primeiro* snapshot que aquela conta/investimento já teve (ela
    ainda não existia/não tinha dado nenhum — contribuição zero está
    correta nesse caso específico).

    Filtro de conta (`is_own`, `include_in_analysis`) e de investimento
    (`is_active`) usa o estado **atual** dessas flags pra todo o histórico,
    mesma simplificação que `load_overview`/`list_investments` já assumem —
    não reconstrói se uma conta virou "não incluir" no meio do período."""
    start_date = reference_date - timedelta(days=days - 1)

    rows = session.execute(
        sa.text(_NET_WORTH_SQL),
        {"start_date": start_date, "end_date": reference_date},
    ).all()

    return [NetWorthPoint(date=row.day, net_worth=row.net_worth) for row in rows]


@dataclass(frozen=True, slots=True)
class CategorySpendDetail:
    name: str
    total: Decimal


@dataclass(frozen=True, slots=True)
class CategorySpendRecord:
    category_id: int
    name: str
    total: Decimal
    details: list[CategorySpendDetail]


def load_category_spend(session: Session, period: str) -> list[CategorySpendRecord]:
    """Gasto por categoria num mês (`direction=OUT`, mesmo predicado de
    "gasto de verdade" da `mv_monthly_cashflow`: POSTED, conta incluída na
    análise, sem transferência interna/pagamento de fatura/exclusão).

    Transação sem `category_id` (a Pluggy não mandou, ou mandou uma
    `pluggy_category` que `category_mapping` não cobre — `resolve_category`
    continua retornando `None` de propósito, isso não muda) entra sob a
    categoria real "Sem categoria" (migration 0011), via `COALESCE` só na
    hora de agrupar — `transaction_classification.category_id` continua
    `NULL` no banco até o usuário reclassificar manualmente pela tela
    (decisão de 2026-08-21: mostrar o buraco em vez de escondê-lo, mesmo
    raciocínio de `resolve_category`).

    Só saídas, sem abater crédito no cartão (estorno, "pula compra"), ao
    contrário do `total_out` da `mv_monthly_cashflow` (regra de domínio 11): o
    banco categoriza o crédito diferente da compra — o "pula compra" da
    academia veio como "Compras" —, e abater por categoria poderia deixar uma
    categoria negativa. Por isso a soma das categorias pode passar do
    `total_out` do mês.

    Sem zero-fill de propósito (diferente do cashflow/planned-vs-actual):
    com ~12 categorias fixas, listar as que não tiveram gasto no mês só
    teria poluído a resposta — decisão de 2026-08-21."""
    fallback_id = session.execute(
        sa.select(Category.id).where(Category.name == "Sem categoria")
    ).scalar_one()

    category_id_expr = sa.func.coalesce(Category.id, fallback_id)
    category_name_expr = sa.func.coalesce(Category.name, "Sem categoria")
    total_expr = sa.func.sum(Transaction.amount_abs)
    expense_filters = (
        Transaction.status == TxStatus.POSTED,
        Transaction.direction == Direction.OUT,
        Account.include_in_analysis,
        sa.func.to_char(Transaction.accrual_date, "YYYY-MM") == period,
        sa.func.coalesce(TransactionClassification.is_internal_transfer, False).is_(False),
        sa.func.coalesce(TransactionClassification.is_card_payment, False).is_(False),
        sa.func.coalesce(TransactionClassification.exclude_from_analysis, False).is_(False),
    )

    rows = session.execute(
        sa.select(
            category_id_expr.label("category_id"),
            category_name_expr.label("name"),
            total_expr.label("total"),
        )
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(
            TransactionClassification,
            TransactionClassification.transaction_id == Transaction.id,
        )
        .outerjoin(Category, Category.id == TransactionClassification.category_id)
        .where(*expense_filters)
        .group_by(category_id_expr, category_name_expr)
        .order_by(total_expr.desc())
    ).all()

    destination_expr = sa.func.coalesce(
        sa.func.nullif(sa.func.trim(Transaction.merchant_name), ""),
        sa.func.nullif(sa.func.trim(Transaction.description), ""),
        "Não identificado",
    )
    detail_total_expr = sa.func.sum(Transaction.amount_abs)
    detail_rows = session.execute(
        sa.select(
            category_id_expr.label("category_id"),
            destination_expr.label("destination"),
            detail_total_expr.label("total"),
        )
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(
            TransactionClassification,
            TransactionClassification.transaction_id == Transaction.id,
        )
        .outerjoin(Category, Category.id == TransactionClassification.category_id)
        .where(*expense_filters)
        .group_by(category_id_expr, destination_expr)
        .order_by(category_id_expr, detail_total_expr.desc())
    ).all()
    details_by_category: dict[int, list[CategorySpendDetail]] = {}
    for row in detail_rows:
        details = details_by_category.setdefault(row.category_id, [])
        if len(details) < 3:
            details.append(CategorySpendDetail(name=row.destination, total=row.total))

    return [
        CategorySpendRecord(
            category_id=row.category_id,
            name=row.name,
            total=row.total,
            details=details_by_category.get(row.category_id, []),
        )
        for row in rows
    ]


def load_health_inputs(
    session: Session, *, reference_date: date, months: int = BURN_RATE_MONTHS
) -> HealthInputs:
    """Junta o que `assess_financial_health` precisa: os últimos `months`
    meses **fechados** de fluxo de caixa, os saldos de hoje, e o total
    planejado vigente por `kind`.

    "Fechado" = termina no mês anterior ao de `reference_date`. O mês
    corrente fica de fora inteiro; o porquê está na docstring de
    `HealthInputs`.

    Diferente de `load_monthly_cashflow`, **não faz zero-fill**: período
    ausente de `mv_monthly_cashflow` simplesmente não entra na lista, e o
    cálculo passa a ser sobre menos meses (`reference_months` na resposta
    conta quais). Mês que você não sincronizava não é mês sem gasto.

    `reference_date` é parâmetro explícito, não `date.today()` interno,
    mesmo motivo de `load_monthly_cashflow`: quem chama decide "hoje", e o
    teste não precisa mockar relógio."""
    periods = _past_periods(_add_months(reference_date, -1), months)

    rows = session.execute(
        sa.text(
            "SELECT period, total_in, total_out FROM mv_monthly_cashflow "
            "WHERE period IN :periods ORDER BY period"
        ).bindparams(sa.bindparam("periods", expanding=True)),
        {"periods": periods},
    ).all()

    overview = load_overview(session)

    planned_rows = session.execute(
        sa.select(PlannedItem.kind, sa.func.sum(PlannedItem.expected_amount).label("total"))
        .where(
            PlannedItem.is_active,
            PlannedItem.valid_from <= reference_date,
            sa.or_(PlannedItem.valid_to.is_(None), PlannedItem.valid_to >= reference_date),
        )
        .group_by(PlannedItem.kind)
    ).all()
    planned_by_kind = {row.kind: row.total for row in planned_rows}

    return HealthInputs(
        months=[
            MonthlyTotals(period=row.period, total_in=row.total_in, total_out=row.total_out)
            for row in rows
        ],
        bank_balance=_total(overview.accounts, "BANK"),
        investments_balance=overview.investments_balance,
        open_credit_card_bill=overview.open_credit_card_bill,
        # `.get` devolvendo None é o caso "não cadastrei", que
        # `_safety_margin` trata diferente de R$ 0 cadastrado.
        planned_income=planned_by_kind.get(PlannedKind.INCOME),
        planned_fixed_expense=planned_by_kind.get(PlannedKind.FIXED_EXPENSE),
        # Mesma janela de 90 dias que o Overview já pedia pro gráfico de
        # patrimônio, pra nota na tela não mudar de valor com a mudança de
        # lugar do cálculo. `_net_worth_trend` descarta os zeros do início.
        net_worth_series=[
            point.net_worth
            for point in load_net_worth_history(
                session, reference_date=reference_date, days=NET_WORTH_TREND_DAYS
            )
        ],
    )
