# Regras do projeto

Regras de domínio, convenções de código, decisões de arquitetura e roadmap do SmartFinance. O desenho completo (modelo de dados, DDL e contrato de endpoints) está em [`arquitetura-app-financas.md`](arquitetura-app-financas.md).

---

## 1. Visão geral

**SmartFinance** é uma aplicação pessoal de análise de saúde financeira. Consome dados bancários reais via **API Pluggy** (conector MeuPluggy, dentro do ecossistema Open Finance regulado), armazena tudo em um Postgres próprio e cruza **gastos planejados × realizados**.

**Usuário único.** Não é produto, não terá outros usuários e não precisa escalar. Essa é uma decisão de escopo, não uma limitação.

### Stack

| Camada | Tecnologia |
|---|---|
| Sync + domínio | Python 3.14, SQLAlchemy 2.0, Pydantic v2 |
| Banco | PostgreSQL |
| API | FastAPI |
| Front | Angular (standalone components + signals) |
| Gráficos | ECharts via `ngx-echarts` |
| Deploy | Kubernetes, nginx servindo o front e fazendo proxy de `/api` |

---

## 2. Regras de domínio

Estas regras determinam se os números do app são verdadeiros. Toda implementação precisa respeitá-las.

1. **Regime de competência.** Compra no cartão pertence ao mês da **compra** (`accrual_date`), não ao mês do pagamento da fatura.
2. **Pagamento de fatura não é despesa.** Marcado como `is_card_payment` e excluído das somas. Contar as duas coisas dobra o gasto.
3. **Transferência entre contas próprias não é despesa.** Detectada por valor igual e oposto, em janela de ±2 dias, entre duas contas com `is_own = true`. Sem isso, mover dinheiro entre contas vira "gasto".
4. **`PENDING` nunca entra em "quanto gastei".** Alimenta só a visão de compromissos futuros.
5. **Nunca `DELETE` em `transaction`.** A API entrega 12 meses de histórico; o Postgres é o arquivo permanente.
6. **Ingestão idempotente.** Rodar o sync duas vezes não pode duplicar nada. Dedup por `pluggy_transaction_id` **e** por `fingerprint` (uma reconexão gera IDs novos para as mesmas transações).
7. **`transaction_classification` é intocável pelo sync.** O worker reescreve `transaction`; as classificações manuais ficam em tabela separada justamente por isso.
8. **Capturar `balance_snapshot` a cada sync.** A API entrega o saldo atual, não uma série histórica. O que não for capturado se perde.
9. **Normalizar o sinal na ingestão.** `direction` (IN/OUT) e `amount_abs` são resolvidos uma única vez. Nenhum `CASE WHEN account.type` espalhado pelas queries.
10. **Filtrar investimentos por `is_active`.** Os inativos são guardados, mas nunca exibidos por padrão.
11. **Crédito no cartão não é receita.** Estorno, "pula compra" e cashback lançados na conta do cartão (`is_card_credit`, resolvido na ingestão) abatem o gasto do mês em que foram lançados. Pagamento de fatura continua fora pela regra 2. As categorias não são abatidas: o banco categoriza o crédito diferente da compra. Consequência aceita: no "pula compra", o gasto sai do mês da compra e volta no mês da cobrança. Revisar quando a primeira cobrança adiada aparecer (fatura de dezembro de 2026).

---

## 3. Convenções de código

### Python

- Type hints obrigatórios, com `mypy` em modo estrito.
- `ruff` para lint e formatação.
- SQLAlchemy 2.0 no estilo `select()`, sem a API `Query` legada.
- Migrations com Alembic. **Nenhuma alteração de schema fora de migration.**
- Pydantic v2 nos schemas da API; models do SQLAlchemy não vazam para os routers.
- `pytest`, com testes obrigatórios para: dedup do sync, detecção de transferência interna, detector de recorrência e matching de regras de orçamento.
- Nenhuma regra de negócio em `api/`. O domínio vive em `core/`.

### Angular

- Standalone components e signals. Nenhum `NgModule` novo.
- Rotas *lazy* por feature.
- Estado do servidor não vai para service global sem necessidade.
- Tipos gerados a partir do `/openapi.json` do FastAPI (Orval), sem interfaces de resposta escritas à mão.
- `LOCALE_ID = 'pt-BR'` com `registerLocaleData(localePt)`.
- Reactive Forms (nunca template-driven) no módulo de orçamento.

### Geral

- Commits no padrão Conventional Commits, em português.
- **Nenhum segredo em código, em `.env` versionado ou em imagem.** `clientId` e `clientSecret` da Pluggy ficam em um Secret do Kubernetes.
- Mensagens de log sem dados financeiros identificáveis.

---

## 4. Decisões de arquitetura

| Decisão | Motivo |
|---|---|
| **A Pluggy é fonte, não banco de dados** | Os dados são copiados para o Postgres a cada sincronização. O dashboard nunca consulta a API da Pluggy por request. |
| **Autenticação obrigatória** | A aplicação nunca é exposta sem login: os dados são o extrato financeiro completo do usuário. |
| **Sem otimização sem gargalo medido** | Nada de cache, fila ou serviço extra enquanto não houver gargalo medido. É um usuário só. |
| **Stack definida** | Alternativas como Streamlit, Next.js e BFF em Node foram avaliadas e descartadas. |

---

## 5. Roadmap

As fases são sequenciais: uma só começa depois que a anterior foi validada. Em particular, as telas do front só vêm depois que a fase 2 está correta.

### Fase 1: Ingestão

Autenticação na Pluggy, leitura de items, accounts e transactions com paginação por cursor, normalização, upsert idempotente, `sync_run` e `sync_cursor`.

**Critério de pronto:** rodar o sync duas vezes seguidas resulta em zero linhas duplicadas, e o histórico de 12 meses está no banco.

### Fase 2: Verdade dos números

Categorias próprias, mapeamento das categorias da Pluggy, detecção de transferência interna e de pagamento de fatura, `mv_monthly_cashflow`.

**Critério de pronto:** o gasto mensal bate com a conferência manual do extrato.

> Esta fase não pode ser pulada. Um dashboard sobre números inflados por transferência interna é pior do que não ter dashboard: ele dá confiança a um número errado.

### Fase 3: Planejado × realizado

`planned_item`, `planned_item_rule`, matching, endpoint de **preview** (dry-run da regra antes de salvar) e telas de orçamento em Angular.

**Critério de pronto:** com salário e gastos fixos cadastrados, a aderência aparece mês a mês.

### Fase 4: Recorrência

Detector próprio (mínimo de 3 ocorrências, intervalo de ~30 ±5 dias, variância de valor ≤ 10% e descrição normalizada), `recurrence_candidate` e promoção a `planned_item`.

### Fase 5: Refinamento

Investimentos, patrimônio líquido, alertas (consentimento expirando, conexão fora de `UPDATED` por 48h) e previsão de saldo.
