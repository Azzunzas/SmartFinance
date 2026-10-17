"""Métricas derivadas de saúde financeira (doc §5).

Módulo puro, no mesmo contrato de `upcoming.py` e `alerts.py`: recebe
agregados já prontos e faz aritmética. Não conhece sessão, SQL nem HTTP —
quem carrega os dados é `core/repository/metrics.py::load_health_inputs`.

**Todo indicador é `Decimal | None`, e `None` quer dizer "não dá pra
calcular" — nunca "zero".** A diferença não é preciosismo: runway `0` é "o
dinheiro acabou", runway `None` é "não sei o seu ritmo de gasto". Um
indicador que devolvesse `0` nos dois casos estaria mentindo num deles, e
seria justamente no caso alarmante que ele mente pra menos.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Doc §5: "burn rate = média de total_out dos últimos 3 meses".
BURN_RATE_MONTHS = 3

#: Janela da tendência patrimonial. 90 dias é o que o gráfico do Overview já
#: pedia — mesma janela pra nota não mudar de valor ao mudar de lugar.
NET_WORTH_TREND_DAYS = 90

_MONEY = Decimal("0.01")
_RATIO = Decimal("0.0001")

# Pesos e cortes da nota. NÃO foram inventados aqui: são exatamente os que o
# front já implementava no `financialHealth()` do Overview em Angular, e
# que o tooltip da tela documenta pro usuário ("saldo mensal vale 50%, cobertura
# da fatura 30% e tendência do patrimônio 20%"). Este módulo é a mudança de
# LUGAR dessa conta, não uma fórmula nova — ver `assess_financial_health`.
_WEIGHT_CASHFLOW = Decimal("0.5")
_WEIGHT_COVERAGE = Decimal("0.3")
_WEIGHT_TREND = Decimal("0.2")

#: Taxa de poupança que já vale nota cheia no componente de fluxo de caixa.
_SAVINGS_RATE_FOR_FULL_SCORE = Decimal("0.2")
#: Quantas vezes a fatura o saldo em conta precisa cobrir pra nota cheia.
_COVERAGE_FOR_FULL_SCORE = Decimal("2")
#: Tendência patrimonial mapeada linearmente de −5% (nota 0) a +5% (nota 100).
_TREND_FLOOR = Decimal("-0.05")
_TREND_SPAN = Decimal("0.1")

_SCORE_HEALTHY = 75
_SCORE_ATTENTION = 50


class HealthStatus(enum.StrEnum):
    """Faixa da nota. Valor em inglês igual ao resto da API (`TxStatus`,
    `Direction`); a tradução é do front, via label pipe — as três strings que a
    tela já usa hoje são "Saudável", "Atenção" e "Crítica"."""

    HEALTHY = "HEALTHY"
    ATTENTION = "ATTENTION"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class MonthlyTotals:
    """Um mês fechado de fluxo de caixa. Espelha `mv_monthly_cashflow`, mas
    declarado aqui de propósito — `core/analysis/` não importa do
    repository, senão a dependência ficaria de mão dupla."""

    period: str
    total_in: Decimal
    total_out: Decimal


@dataclass(frozen=True, slots=True)
class HealthInputs:
    """Pré-requisito de quem chama, igual ao de `MatchableTransaction`:
    `months` traz só meses **fechados**, e só os que existem de verdade.

    Duas armadilhas que essa exigência evita, e que quem monta a lista
    precisa conhecer:

    1. **Mês corrente.** Hoje dia 24, agosto tem 24 dias de gasto e 31 de
       calendário. Entrar na média como se fosse mês inteiro puxa o burn
       rate pra baixo e infla o runway — número otimista e errado, e o erro
       é maior quanto mais cedo no mês você olha.
    2. **Mês sem dado.** Um período ausente da view não é um mês em que
       você não gastou nada; é um mês em que você ainda não sincronizava.
       Preencher com zero tem o mesmo efeito do item 1. Por isso a lista é
       filtrada, não zero-fillada — decisão oposta à de
       `load_monthly_cashflow`, que zera de propósito pro gráfico não ter
       buraco. Gráfico com buraco é feio; média com zero falso é mentira.
    """

    months: Sequence[MonthlyTotals]
    bank_balance: Decimal
    investments_balance: Decimal
    open_credit_card_bill: Decimal
    # `None` = nada cadastrado, distinto de R$ 0 cadastrado. Ver
    # `_safety_margin` pro porquê da distinção importar aqui.
    planned_income: Decimal | None
    planned_fixed_expense: Decimal | None
    #: Patrimônio líquido dia a dia, mais antigo primeiro (90 dias por padrão).
    #: Alimenta só o componente de tendência da nota. Pode vir vazia.
    net_worth_series: Sequence[Decimal] = ()


@dataclass(frozen=True, slots=True)
class FinancialHealth:
    #: Meses de fato usados no cálculo. Vai na resposta da API porque sem
    #: isso "burn rate R$ 1.200" é um número sem procedência — o leitor não
    #: sabe se são 3 meses ou 1.
    reference_months: list[str]
    available_cash: Decimal
    savings_rate: Decimal | None
    burn_rate: Decimal | None
    runway_months: Decimal | None
    fixed_cost_monthly: Decimal | None
    safety_margin: Decimal | None
    #: Nota 0–100 e sua faixa. `None` quando não dá pra calcular — a tela já
    #: tem estado próprio pra isso ("Ainda não há três meses completos com
    #: renda para calcular o indicador").
    score: int | None
    status: HealthStatus | None
    #: Os dois componentes da nota que ainda não existiam como métrica
    #: própria. `savings_rate` é o terceiro, e já estava acima.
    bill_coverage: Decimal | None
    net_worth_trend: Decimal | None


def assess_financial_health(inputs: HealthInputs) -> FinancialHealth:
    """As cinco métricas da §5 (taxa de poupança, burn rate, runway, custo
    fixo mensal e margem de segurança) mais a **nota agregada** de saúde.

    Sobre a nota, e por que ela existe aqui desde 2026-08-24: quando este
    módulo nasceu, mais cedo no mesmo dia, ela ficou de fora com a
    justificativa de que "os pesos são arbitrários e ninguém definiu". Isso
    estava **errado**: o front já tinha a fórmula inteira implementada
    dentro do `financialHealth()` do Overview em Angular, com o tooltip da
    tela documentando os pesos pro usuário. Os pesos existiam; o lugar é que
    estava errado.

    Trazer pra cá é a §6.1 do doc de arquitetura aplicada ao pé da letra —
    ela usa *exatamente* a taxa de poupança como exemplo do que não pode ser
    calculado fora do domínio, sob pena de "os dois números divergirem". E
    eles já divergiam numa condição concreta: o front somava a série de
    `/api/metrics/cashflow`, que faz zero-fill, então mês sem sync entrava
    como R$ 0 de receita e afundava a nota. Aqui os meses vêm filtrados
    (ver `HealthInputs`).

    **A fórmula é portada fiel, não redesenhada** — mesmos pesos (50/30/20),
    mesmos cortes (75/50), mesmos mapeamentos lineares. Só a entrada
    melhorou. Assim a nota na tela não muda de valor por causa da mudança de
    lugar, e qualquer ajuste de critério vira uma decisão separada e
    visível."""
    months = list(inputs.months)
    available_cash = _available_cash(inputs)
    burn_rate = _burn_rate(months)
    savings_rate = _savings_rate(months)
    bill_coverage = _bill_coverage(inputs.bank_balance, inputs.open_credit_card_bill)
    net_worth_trend = _net_worth_trend(inputs.net_worth_series)
    score = _score(savings_rate, bill_coverage, net_worth_trend)

    return FinancialHealth(
        reference_months=[month.period for month in months],
        available_cash=_money(available_cash),
        savings_rate=savings_rate,
        burn_rate=burn_rate,
        runway_months=_runway_months(available_cash, burn_rate),
        fixed_cost_monthly=(
            None if inputs.planned_fixed_expense is None else _money(inputs.planned_fixed_expense)
        ),
        safety_margin=_safety_margin(inputs.planned_income, inputs.planned_fixed_expense),
        score=score,
        status=None if score is None else _status(score),
        bill_coverage=bill_coverage,
        net_worth_trend=net_worth_trend,
    )


def _available_cash(inputs: HealthInputs) -> Decimal:
    """Contas + investimentos − **fatura de cartão em aberto**.

    Diverge da §5, que escreve só "saldo em contas + investimentos
    líquidos". Decisão de 2026-08-24: a fatura é dívida certa, com data
    marcada, e boa parte dela já foi gasta em regime de competência. Contar
    esse dinheiro como disponível é contar como seu um dinheiro que já tem
    dono — e o efeito seria inflar exatamente o indicador (runway) que
    existe pra avisar quando o dinheiro está acabando.

    É a mesma composição do patrimônio líquido de `load_overview`, e não
    por acaso: é a mesma pergunta ("quanto é meu de verdade")."""
    return inputs.bank_balance + inputs.investments_balance - inputs.open_credit_card_bill


def _burn_rate(months: Sequence[MonthlyTotals]) -> Decimal | None:
    """Média simples de `total_out` dos meses recebidos. `None` sem mês
    nenhum — média de lista vazia não é zero, é indefinida."""
    if not months:
        return None
    total_out = sum((month.total_out for month in months), Decimal(0))
    return _money(total_out / len(months))


def _savings_rate(months: Sequence[MonthlyTotals]) -> Decimal | None:
    """`net / total_in` (doc §5), agregado sobre a janela inteira em vez de
    média das taxas mensais.

    Agregar pondera pela renda, que é o que a métrica quer dizer: um mês de
    renda alta e um de renda baixa não contribuem igual pra "quanto do que
    entrou eu consegui guardar". A média das taxas daria o mesmo peso aos
    dois.

    Devolve fração (`0.2345`), não percentual — formatação é problema da
    tela. Pode ser negativo: gastar mais do que entrou é resultado válido, e
    justamente o que você precisa ver."""
    total_in = sum((month.total_in for month in months), Decimal(0))
    if total_in == 0:
        return None
    total_out = sum((month.total_out for month in months), Decimal(0))
    return _ratio((total_in - total_out) / total_in)


def _runway_months(available_cash: Decimal, burn_rate: Decimal | None) -> Decimal | None:
    """Quantos meses o dinheiro disponível cobre no ritmo atual de gasto.

    `None` quando não há burn rate (sem histórico) **ou** quando ele é zero:
    dividir por zero daria "infinito", e um mês fechado com gasto zero é
    quase certamente falta de dado, não frugalidade.

    Caixa negativo devolve `0`, não um número negativo: "-2,3 meses" não
    quer dizer nada. Zero aqui lê como "já está no vermelho", que é o
    recado certo — o tamanho do buraco você vê no patrimônio líquido."""
    if burn_rate is None or burn_rate == 0:
        return None
    if available_cash <= 0:
        return Decimal("0.00")
    return _money(available_cash / burn_rate)


def _safety_margin(income: Decimal | None, fixed_cost: Decimal | None) -> Decimal | None:
    """`(renda − custo fixo) / renda` (doc §5), os dois lados vindo do
    **planejado** (`planned_item` vigente), não do realizado.

    Coerência: custo fixo só existe como plano, então comparar com renda
    realizada misturaria as duas fontes — e a renda realizada inclui
    qualquer entrada eventual (PIX recebido, reembolso), o que faria a
    margem parecer melhor do que é.

    `None` se faltar **qualquer** dos dois lados. Sem `FIXED_EXPENSE`
    cadastrado a conta daria 100% de margem, que é a resposta mais errada
    possível: ela não significa "não tenho custo fixo", significa "não
    cadastrei meus custos fixos" — e diria isso com a cara de quem está
    ótimo."""
    if income is None or income == 0 or fixed_cost is None:
        return None
    return _ratio((income - fixed_cost) / income)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO, rounding=ROUND_HALF_UP)


def _bill_coverage(bank_balance: Decimal, open_credit_card_bill: Decimal) -> Decimal:
    """Quantas vezes o saldo em conta cobre a fatura em aberto.

    Só saldo de conta corrente, não patrimônio: a pergunta é "se a fatura
    vencesse hoje, o dinheiro líquido daria?". Investimento pode não estar
    resgatável a tempo.

    Fatura zerada devolve `1` (cobertura exata), portado fiel do front.
    **Discutível, e registrado como tal:** não dever nada devolve meia nota
    nesse componente, quando o intuitivo seria nota cheia. Ficou como está
    porque mudar junto com a mudança de lugar misturaria duas coisas — a
    nota na tela não pode mudar de valor só porque a conta trocou de
    arquivo. Vira decisão separada se incomodar."""
    if open_credit_card_bill <= 0:
        return Decimal(1)
    return _ratio(bank_balance / open_credit_card_bill)


def _net_worth_trend(series: Sequence[Decimal]) -> Decimal | None:
    """Variação relativa do patrimônio entre a primeira leitura conhecida e a
    última.

    Descarta os zeros do começo da série antes de medir: dia sem snapshot vem
    zerado de `load_net_worth_history`, e começar a régua num zero falso daria
    uma variação absurda. Mesma família da decisão de não zero-fillar mês em
    `HealthInputs` — dado ausente não é dado valendo zero.

    `None` com menos de dois pontos conhecidos, ou quando o primeiro é zero
    (não há base pra dividir)."""
    known = list(series)
    while known and known[0] == 0:
        known.pop(0)
    if len(known) < 2:
        return None
    base = abs(known[0])
    if base == 0:
        return None
    return _ratio((known[-1] - known[0]) / base)


def _score(
    savings_rate: Decimal | None,
    bill_coverage: Decimal | None,
    net_worth_trend: Decimal | None,
) -> int | None:
    """Nota 0–100: 50% fluxo de caixa, 30% cobertura da fatura, 20% tendência
    patrimonial. Pesos e mapeamentos portados do front (ver
    `assess_financial_health`).

    `None` sem taxa de poupança — sem renda no período não há o componente que
    sozinho vale metade da nota, e a tela já trata esse caso com texto
    próprio. Os outros dois componentes ausentes contam **zero** em vez de
    anular a nota inteira: patrimônio sem histórico é situação normal em
    instalação nova, e derrubar o indicador todo por causa disso esconderia os
    50% que dão pra medir."""
    if savings_rate is None:
        return None

    cashflow_score = _clamp(savings_rate / _SAVINGS_RATE_FOR_FULL_SCORE * 100)
    coverage_score = (
        Decimal(0)
        if bill_coverage is None
        else _clamp(bill_coverage / _COVERAGE_FOR_FULL_SCORE * 100)
    )
    trend_score = (
        Decimal(0)
        if net_worth_trend is None
        else _clamp((net_worth_trend - _TREND_FLOOR) / _TREND_SPAN * 100)
    )

    total = (
        cashflow_score * _WEIGHT_CASHFLOW
        + coverage_score * _WEIGHT_COVERAGE
        + trend_score * _WEIGHT_TREND
    )
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _status(score: int) -> HealthStatus:
    if score >= _SCORE_HEALTHY:
        return HealthStatus.HEALTHY
    if score >= _SCORE_ATTENTION:
        return HealthStatus.ATTENTION
    return HealthStatus.CRITICAL


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal(0), min(Decimal(100), value))
