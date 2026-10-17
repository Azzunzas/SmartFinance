from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.analysis.classify import is_card_payment, resolve_category
from core.analysis.internal_transfer import (
    TransferCandidate,
    is_transfer_eligible,
    match_internal_transfers,
)
from core.analysis.planned_matching import match_planned_items
from core.analysis.recurrence import detect_recurrence
from core.repository.analysis import (
    load_matchable_transactions,
    load_transactions_for_analysis,
    refresh_monthly_cashflow,
)
from core.repository.categories import load_category_mapping
from core.repository.classification import (
    ClassificationUpsert,
    count_manual_overrides,
    upsert_auto_classification,
)
from core.repository.planned_items import list_all_rules_for_matching, replace_planned_item_matches
from core.repository.recurrence import upsert_recurrence_candidates


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    transactions_processed: int
    classified: int
    manual_overrides: int
    internal_transfer_pairs: int
    recurrence_candidates: int
    planned_item_matches: int


def run_analysis(session: Session) -> AnalysisResult:
    """Reprocessa a classificação de TODAS as transações — não é incremental
    de propósito (doc §2: "precisa poder ser reexecutada sozinha... idempotente
    por definição"). Pra um usuário só, com milhares de transações, recalcular
    tudo do zero cada vez é mais simples e barato do que rastrear "o que mudou
    desde a última vez", sem gargalo medido que justifique a complexidade."""
    mapping = load_category_mapping(session)
    transactions = load_transactions_for_analysis(session)

    candidates = [
        TransferCandidate(
            transaction_id=t.transaction_id,
            account_id=t.account_id,
            date=t.date,
            amount_abs=t.amount_abs,
            direction=t.direction,
        )
        for t in transactions
        # A regra de quem é elegível mora no `core/analysis/`, não numa condição
        # solta aqui: é decisão de domínio, e domínio precisa de teste próprio.
        if is_transfer_eligible(
            is_own_account=t.is_own_account, account_type=t.account_type, direction=t.direction
        )
    ]
    matches = match_internal_transfers(candidates)

    transfer_partner: dict[int, int] = {}
    for m in matches:
        transfer_partner[m.out_transaction_id] = m.in_transaction_id
        transfer_partner[m.in_transaction_id] = m.out_transaction_id

    # Todas são classificadas, sem exceção. Antes da migration 0013 uma linha
    # marcada MANUAL era pulada aqui e nunca mais reclassificada; hoje o
    # automático escreve nas colunas `_auto` dele e o seu override continua
    # vencendo na leitura, então não existe mais "pulada".
    for t in transactions:
        category = resolve_category(t.pluggy_category, mapping)
        upsert_auto_classification(
            session,
            ClassificationUpsert(
                transaction_id=t.transaction_id,
                category_id=category.category_id if category else None,
                is_internal_transfer=t.transaction_id in transfer_partner,
                is_card_payment=is_card_payment(category, t.description_norm),
                counterpart_tx_id=transfer_partner.get(t.transaction_id),
            ),
        )

    refresh_monthly_cashflow(session)

    # Depois da classificação: o detector precisa do pool "gasto de verdade"
    # (exclui transferência interna/pagamento de fatura), que só existe
    # depois que a classificação acima já rodou nesta mesma sessão.
    matchable = load_matchable_transactions(session)
    recurrence_candidates = detect_recurrence(matchable)
    upsert_recurrence_candidates(session, recurrence_candidates)

    rules = list_all_rules_for_matching(session)
    planned_item_matches = match_planned_items(matchable, rules)
    replace_planned_item_matches(session, planned_item_matches)

    return AnalysisResult(
        transactions_processed=len(transactions),
        classified=len(transactions),
        manual_overrides=count_manual_overrides(session),
        internal_transfer_pairs=len(matches),
        recurrence_candidates=len(recurrence_candidates),
        planned_item_matches=len(planned_item_matches),
    )
