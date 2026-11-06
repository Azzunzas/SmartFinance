from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.metrics import (
    CategorySpendOut,
    FinancialHealthOut,
    MonthlyCashflowOut,
    NetWorthPointOut,
    OverviewOut,
    PlannedVsActualOut,
)
from api.schemas.upcoming import MonthlyCommitmentOut
from core.analysis.health import assess_financial_health
from core.analysis.upcoming import project_upcoming
from core.repository.analysis import load_upcoming_transactions
from core.repository.bills import load_upcoming_bills
from core.repository.metrics import (
    load_category_spend,
    load_health_inputs,
    load_monthly_cashflow,
    load_net_worth_history,
    load_overview,
    load_planned_vs_actual,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/overview", response_model=OverviewOut)
def overview(session: Session = Depends(get_session)) -> OverviewOut:
    return OverviewOut.model_validate(load_overview(session))


@router.get("/upcoming", response_model=list[MonthlyCommitmentOut])
def upcoming(
    months: int = 6, session: Session = Depends(get_session)
) -> list[MonthlyCommitmentOut]:
    """Doc §6.2: `PENDING` + parcelas projetadas + faturas fechadas a vencer,
    por mês, a partir de hoje."""
    commitments = project_upcoming(
        load_upcoming_transactions(session),
        bills=load_upcoming_bills(session),
        reference_date=datetime.now(UTC).date(),
        months=months,
    )
    return [MonthlyCommitmentOut.model_validate(c) for c in commitments]


@router.get("/planned-vs-actual", response_model=list[PlannedVsActualOut])
def planned_vs_actual(
    period: str = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
) -> list[PlannedVsActualOut]:
    """Doc §6.2: `GET /api/metrics/planned-vs-actual?period=`. Sem `period`,
    usa o mês corrente. `matched_amount` vem do que `run_analysis` já gravou
    em `planned_item_match` — este endpoint só lê e agrega, não recalcula
    nada na hora da request."""
    if period is None:
        period = datetime.now(UTC).date().strftime("%Y-%m")
    records = load_planned_vs_actual(session, period)
    return [PlannedVsActualOut.model_validate(r) for r in records]


@router.get("/cashflow", response_model=list[MonthlyCashflowOut])
def cashflow(
    months: int = 6,
    order: Literal["asc", "desc"] = "asc",
    session: Session = Depends(get_session),
) -> list[MonthlyCashflowOut]:
    """Doc §9: fluxo de caixa mensal, lido de `mv_monthly_cashflow`.
    `order="asc"` (padrão) é mais-antigo-primeiro, mesma convenção de
    `/upcoming`."""
    records = load_monthly_cashflow(
        session, reference_date=datetime.now(UTC).date(), months=months, order=order
    )
    return [MonthlyCashflowOut.model_validate(r) for r in records]


@router.get("/networth", response_model=list[NetWorthPointOut])
def networth(days: int = 90, session: Session = Depends(get_session)) -> list[NetWorthPointOut]:
    """Doc §9: patrimônio líquido histórico, um ponto por dia. Forward-fill
    por conta/investimento a partir do último snapshot conhecido até cada
    dia (ver docstring de `load_net_worth_history`) — dia sem sync não é
    saldo zero."""
    records = load_net_worth_history(session, reference_date=datetime.now(UTC).date(), days=days)
    return [NetWorthPointOut.model_validate(r) for r in records]


@router.get("/categories", response_model=list[CategorySpendOut])
def categories(
    period: str = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
) -> list[CategorySpendOut]:
    """Doc §9: gasto por categoria num mês. Sem `period`, usa o mês
    corrente. Só categorias com gasto de verdade aparecem — sem zero-fill,
    diferente do cashflow/planned-vs-actual (ver docstring de
    `load_category_spend`)."""
    if period is None:
        period = datetime.now(UTC).date().strftime("%Y-%m")
    records = load_category_spend(session, period)
    return [CategorySpendOut.model_validate(r) for r in records]


@router.get("/health", response_model=FinancialHealthOut)
def health(session: Session = Depends(get_session)) -> FinancialHealthOut:
    """Doc §5: taxa de poupança, burn rate, runway, custo fixo mensal e
    margem de segurança. Indicador incalculável vem `null`, não zero — ver
    a docstring de `core/analysis/health.py` pro porquê."""
    inputs = load_health_inputs(session, reference_date=datetime.now(UTC).date())
    return FinancialHealthOut.model_validate(assess_financial_health(inputs))
