from decimal import Decimal

from core.analysis.health import (
    FinancialHealth,
    HealthInputs,
    HealthStatus,
    MonthlyTotals,
    assess_financial_health,
)


def _month(period: str, *, total_in: str, total_out: str) -> MonthlyTotals:
    return MonthlyTotals(period=period, total_in=Decimal(total_in), total_out=Decimal(total_out))


def _inputs(
    *,
    months: list[MonthlyTotals] | None = None,
    bank_balance: str = "10000.00",
    investments_balance: str = "0.00",
    open_credit_card_bill: str = "0.00",
    planned_income: str | None = None,
    planned_fixed_expense: str | None = None,
    net_worth_series: list[str] | None = None,
) -> HealthInputs:
    return HealthInputs(
        months=months if months is not None else [],
        bank_balance=Decimal(bank_balance),
        investments_balance=Decimal(investments_balance),
        open_credit_card_bill=Decimal(open_credit_card_bill),
        planned_income=None if planned_income is None else Decimal(planned_income),
        planned_fixed_expense=(
            None if planned_fixed_expense is None else Decimal(planned_fixed_expense)
        ),
        net_worth_series=[Decimal(v) for v in (net_worth_series or [])],
    )


_THREE_MONTHS = [
    _month("2026-05", total_in="3000.00", total_out="2000.00"),
    _month("2026-06", total_in="3000.00", total_out="2500.00"),
    _month("2026-07", total_in="3000.00", total_out="1500.00"),
]


def test_burn_rate_is_the_average_of_the_months_received() -> None:
    result = assess_financial_health(_inputs(months=_THREE_MONTHS))

    assert result.burn_rate == Decimal("2000.00")
    assert result.reference_months == ["2026-05", "2026-06", "2026-07"]


def test_savings_rate_aggregates_the_window_instead_of_averaging_rates() -> None:
    """Meses de renda diferente não podem pesar igual. Aqui a renda é a
    mesma nos três, então o agregado é direto: entrou 9000, saiu 6000."""
    result = assess_financial_health(_inputs(months=_THREE_MONTHS))

    assert result.savings_rate == Decimal("0.3333")


def test_savings_rate_is_negative_when_you_spend_more_than_you_earn() -> None:
    result = assess_financial_health(
        _inputs(months=[_month("2026-07", total_in="1000.00", total_out="1500.00")])
    )

    assert result.savings_rate == Decimal("-0.5000")


def test_savings_rate_is_none_without_income() -> None:
    """Divisão por zero. `None` porque a taxa é indefinida, não 0% —
    0% diria "não guardei nada", que é afirmação diferente."""
    result = assess_financial_health(
        _inputs(months=[_month("2026-07", total_in="0.00", total_out="500.00")])
    )

    assert result.savings_rate is None


def test_runway_discounts_the_open_credit_card_bill() -> None:
    """Decisão de 2026-08-24, divergente da §5 literal: a fatura é dívida
    certa. Sem descontar dariam 6 meses; com desconto, 4."""
    result = assess_financial_health(
        _inputs(
            months=_THREE_MONTHS,
            bank_balance="10000.00",
            investments_balance="2000.00",
            open_credit_card_bill="4000.00",
        )
    )

    assert result.available_cash == Decimal("8000.00")
    assert result.runway_months == Decimal("4.00")


def test_runway_is_zero_when_the_cash_is_already_negative() -> None:
    result = assess_financial_health(
        _inputs(months=_THREE_MONTHS, bank_balance="1000.00", open_credit_card_bill="3000.00")
    )

    assert result.available_cash == Decimal("-2000.00")
    assert result.runway_months == Decimal("0.00")


def test_runway_is_none_when_there_is_no_burn_rate() -> None:
    """Sem mês fechado não há ritmo de gasto conhecido. Devolver um número
    grande ("infinito") seria o pior erro possível nesse indicador."""
    result = assess_financial_health(_inputs(months=[]))

    assert result.burn_rate is None
    assert result.runway_months is None


def test_runway_is_none_when_the_burn_rate_is_zero() -> None:
    """Mês fechado com gasto zero é quase certamente falta de dado, não
    frugalidade — e dividir por zero não tem resposta."""
    result = assess_financial_health(
        _inputs(months=[_month("2026-07", total_in="3000.00", total_out="0.00")])
    )

    assert result.burn_rate == Decimal("0.00")
    assert result.runway_months is None


def test_safety_margin_uses_the_planned_side_of_both_terms() -> None:
    result = assess_financial_health(
        _inputs(months=_THREE_MONTHS, planned_income="5000.00", planned_fixed_expense="2000.00")
    )

    assert result.fixed_cost_monthly == Decimal("2000.00")
    assert result.safety_margin == Decimal("0.6000")


def test_safety_margin_is_none_without_fixed_expenses_registered() -> None:
    """Cenário: só um `planned_item` INCOME cadastrado, nenhum custo fixo.
    A conta daria 100% de margem, que leria como "estou ótimo" quando o que
    aconteceu foi "os custos fixos não foram cadastrados"."""
    result = assess_financial_health(_inputs(months=_THREE_MONTHS, planned_income="1500.00"))

    assert result.fixed_cost_monthly is None
    assert result.safety_margin is None


def test_safety_margin_is_none_without_income_registered() -> None:
    result = assess_financial_health(_inputs(months=_THREE_MONTHS, planned_fixed_expense="2000.00"))

    assert result.fixed_cost_monthly == Decimal("2000.00")
    assert result.safety_margin is None


def test_everything_is_none_on_an_empty_database() -> None:
    """Instalação nova: nenhum indicador inventa número."""
    result = assess_financial_health(_inputs(months=[], bank_balance="0.00"))

    assert result == FinancialHealth(
        reference_months=[],
        available_cash=Decimal("0.00"),
        savings_rate=None,
        burn_rate=None,
        runway_months=None,
        fixed_cost_monthly=None,
        safety_margin=None,
        score=None,
        status=None,
        bill_coverage=Decimal("1"),
        net_worth_trend=None,
    )


def test_score_reproduces_the_formula_the_front_already_used() -> None:
    """A nota foi **portada**, não redesenhada: 50% fluxo de caixa, 30%
    cobertura da fatura, 20% tendência. Cenário escolhido pra dar nota cheia
    nos três componentes."""
    result = assess_financial_health(
        _inputs(
            months=[_month("2026-07", total_in="1000.00", total_out="700.00")],  # poupança 30%
            bank_balance="4000.00",
            open_credit_card_bill="1000.00",  # cobertura 4x
            net_worth_series=["1000.00", "1100.00"],  # tendência +10%
        )
    )

    assert result.savings_rate == Decimal("0.3000")
    assert result.bill_coverage == Decimal("4.0000")
    assert result.net_worth_trend == Decimal("0.1000")
    assert result.score == 100
    assert result.status is HealthStatus.HEALTHY


def test_score_matches_the_real_overview_numbers_of_2026_08_24() -> None:
    """Réplica do estado real do banco no dia da migração do cálculo, com os
    três componentes no chão. A tela mostrava 0/Crítica antes da mudança de
    lugar, e precisa continuar mostrando."""
    result = assess_financial_health(
        _inputs(
            months=[
                _month("2026-05", total_in="2506.99", total_out="2800.19"),
                _month("2026-06", total_in="2221.65", total_out="2280.74"),
                _month("2026-07", total_in="3038.15", total_out="3298.04"),
            ],
            bank_balance="7.08",
            open_credit_card_bill="1689.29",
            net_worth_series=["-1390.00", "-1682.21"],
        )
    )

    assert result.savings_rate == Decimal("-0.0788")
    assert result.score == 0
    assert result.status is HealthStatus.CRITICAL


def test_score_thresholds_pick_the_status_band() -> None:
    """Cortes em 75 e 50, portados do front. Cada cenário é montado pelos três
    componentes: poupança/0,2, cobertura/2 e (tendência+0,05)/0,1, tudo
    limitado a 0–100 e pesado 50/30/20."""
    # poupança 10% -> 50 pts (x0,5=25) | cobertura 1x -> 50 (x0,3=15)
    # tendência 0% -> 50 (x0,2=10)  ==> 50, na borda de ATTENTION
    atencao = assess_financial_health(
        _inputs(
            months=[_month("2026-07", total_in="1000.00", total_out="900.00")],
            bank_balance="1000.00",
            open_credit_card_bill="1000.00",
            net_worth_series=["1000.00", "1000.00"],
        )
    )
    assert atencao.score == 50
    assert atencao.status is HealthStatus.ATTENTION

    # poupança 30% -> 100 (50) | cobertura 4x -> 100 (30) | tendência +10% -> 100 (20)
    saudavel = assess_financial_health(
        _inputs(
            months=[_month("2026-07", total_in="1000.00", total_out="700.00")],
            bank_balance="4000.00",
            open_credit_card_bill="1000.00",
            net_worth_series=["1000.00", "1100.00"],
        )
    )
    assert saudavel.score == 100
    assert saudavel.status is HealthStatus.HEALTHY

    # poupança 0% -> 0 | cobertura 0 -> 0 | tendência -10% -> 0
    critico = assess_financial_health(
        _inputs(
            months=[_month("2026-07", total_in="1000.00", total_out="1000.00")],
            bank_balance="0.00",
            open_credit_card_bill="1000.00",
            net_worth_series=["1000.00", "900.00"],
        )
    )
    assert critico.score == 0
    assert critico.status is HealthStatus.CRITICAL


def test_score_is_none_without_income_but_other_metrics_survive() -> None:
    """Sem renda no período não há o componente que vale metade da nota. A
    tela tem texto próprio pra esse caso — devolver um número seria pior."""
    result = assess_financial_health(
        _inputs(months=[_month("2026-07", total_in="0.00", total_out="500.00")])
    )

    assert result.score is None
    assert result.status is None
    assert result.burn_rate == Decimal("500.00")


def test_net_worth_trend_ignores_leading_days_without_snapshot() -> None:
    """`load_net_worth_history` devolve zero pro dia sem snapshot. Começar a
    régua num zero falso daria variação absurda — mesma família da decisão de
    não zero-fillar mês."""
    result = assess_financial_health(
        _inputs(
            months=_THREE_MONTHS,
            net_worth_series=["0.00", "0.00", "2000.00", "2400.00"],
        )
    )

    assert result.net_worth_trend == Decimal("0.2000")


def test_net_worth_trend_is_none_with_a_single_known_point() -> None:
    result = assess_financial_health(
        _inputs(months=_THREE_MONTHS, net_worth_series=["0.00", "2000.00"])
    )

    assert result.net_worth_trend is None
