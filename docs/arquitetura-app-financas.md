# App de Saúde Financeira Pessoal — Arquitetura e Modelo de Dados

> Fonte de dados: API Pluggy via conector **MeuPluggy (200)**, uso pessoal.
> Stack sugerida: Python (sync + análise), PostgreSQL, backend HTTP, frontend web.

---

## 1. Princípios que guiam o desenho

| # | Princípio | Consequência prática |
|---|---|---|
| 1 | **A Pluggy é fonte, não banco de dados** | A doc é explícita: transações devem ser copiadas para os seus sistemas, uma leitura por sincronização. Nada de consulta on-demand na API a cada request do dashboard. |
| 2 | **Seu banco é o arquivo de longo prazo** | A API retorna no máximo 12 meses. Depois do primeiro sync, seu Postgres tem histórico que a Pluggy não tem mais. **Nunca faça DELETE em transações.** |
| 3 | **Ingestão idempotente** | Todo sync pode rodar duas vezes sem duplicar nada. Upsert por chave natural + fingerprint. |
| 4 | **Camada bruta ≠ camada analítica** | Guarde o JSON original intacto. Reprocessar categorização/regras não deve exigir re-fetch. |
| 5 | **Regime de competência** | Compra no cartão pertence ao mês da compra. Pagamento de fatura é transferência interna, não despesa. |

---

## 2. Arquitetura de componentes

```
                        ┌──────────────────────────┐
                        │   API Pluggy (externa)   │
                        │  /auth  /items  /accounts│
                        │  /v2/transactions        │
                        │  /investments            │
                        └────────────┬─────────────┘
                                     │ HTTPS (apiKey de curta duração)
                                     ▼
┌────────────────────────────────────────────────────────────────┐
│  SYNC WORKER  (Python · K8s CronJob · 1x/dia)                  │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ Auth     │─▶│ Fetch     │─▶│ Normalize │─▶│ Upsert       │  │
│  │ apiKey   │  │ (cursor)  │  │ + sign    │  │ (idempotente)│  │
│  └──────────┘  └───────────┘  └───────────┘  └──────┬───────┘  │
└─────────────────────────────────────────────────────┼──────────┘
                                                      ▼
                        ┌───────────────────────────────────────┐
                        │           PostgreSQL                  │
                        │  raw · núcleo · classificação ·       │
                        │  orçamento · agregados materializados │
                        └───────────────┬───────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                         ▼
   ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
   │ ANALYSIS ENGINE    │   │  BACKEND API       │   │  ALERTAS           │
   │ (job pós-sync)     │   │  (FastAPI)         │   │  consentimento     │
   │ · transf. internas │   │  · endpoints de    │   │  a expirar,        │
   │ · recorrências     │   │    métricas        │   │  conexão quebrada, │
   │ · match orçamento  │   │  · CRUD orçamento  │   │  gasto fora        │
   │ · refresh das MVs  │   │                    │   │  do padrão         │
   └────────────────────┘   └─────────┬──────────┘   └────────────────────┘
                                      ▼
                            ┌────────────────────┐
                            │  FRONTEND (Angular)│
                            │  visão geral ·     │
                            │  fluxo de caixa ·  │
                            │  planejado × real  │
                            └────────────────────┘
```

### Por que o Analysis Engine é separado do Sync

Sync é I/O-bound e pode falhar por causa da Pluggy. Análise é CPU-bound sobre dados locais e precisa poder ser **reexecutada sozinha** — toda vez que você mudar uma regra de orçamento ou reclassificar uma categoria, você quer reprocessar sem tocar na API externa. Acoplar os dois te obriga a re-fetch para corrigir uma regex.

### Cadência

| Job | Frequência | Observação |
|---|---|---|
| `sync:full` | manual / 1ª execução | Puxa os 12 meses disponíveis |
| `sync:incremental` | diária (ex.: 06:00) | Open Finance atualiza diariamente; mais que isso é desperdício |
| `analysis:recompute` | pós-sync + sob demanda | Idempotente por definição |
| `check:consent` | diária | Consentimento OF expira em até 365 dias |

---

## 3. Modelo de dados

### 3.1 Visão de relacionamentos

```
connection (item)
   │ 1:N
   ├──▶ account ──┬─ 1:N ─▶ transaction ──┬─ 1:1 ─▶ transaction_classification
   │              │                       └─ N:1 ─▶ category
   │              └─ 1:N ─▶ balance_snapshot
   │
   └──▶ investment ── 1:N ─▶ investment_snapshot

planned_item ──┬─ 1:N ─▶ planned_item_rule
               └─ 1:N ─▶ planned_item_match ──▶ transaction

recurrence_candidate  (saída do detector, vira sugestão de planned_item)
sync_run              (auditoria)
```

### 3.2 DDL (PostgreSQL)

#### Camada de conexão

```sql
CREATE TABLE connection (                    -- "item" na nomenclatura Pluggy
    id                  BIGSERIAL PRIMARY KEY,
    pluggy_item_id      UUID        NOT NULL UNIQUE,
    connector_id        INTEGER     NOT NULL,
    connector_name      TEXT        NOT NULL,
    status              TEXT        NOT NULL,   -- UPDATED / OUTDATED / LOGIN_ERROR / WAITING_USER_INPUT
    execution_status    TEXT,
    last_updated_at     TIMESTAMPTZ,
    consent_expires_at  TIMESTAMPTZ,            -- alerta quando faltar < 30 dias
    superseded_by       BIGINT REFERENCES connection(id),  -- reconexão: aponta pro item novo
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                 JSONB       NOT NULL
);
```

> `superseded_by` é o que preserva a linhagem quando você reconecta um banco: o item antigo continua existindo (histórico), mas as contas migram para o novo.

#### Contas

```sql
CREATE TABLE account (
    id                    BIGSERIAL PRIMARY KEY,
    connection_id         BIGINT      NOT NULL REFERENCES connection(id),
    pluggy_account_id     UUID        NOT NULL UNIQUE,
    fingerprint           TEXT        NOT NULL,   -- estável entre reconexões (ver §4.2)
    type                  TEXT        NOT NULL,   -- BANK | CREDIT
    subtype               TEXT,                   -- CHECKING_ACCOUNT | SAVINGS_ACCOUNT | CREDIT_CARD
    name                  TEXT,
    number_masked         TEXT,
    currency_code         CHAR(3)     NOT NULL DEFAULT 'BRL',
    balance               NUMERIC(14,2),
    credit_limit          NUMERIC(14,2),
    available_credit_limit NUMERIC(14,2),
    is_own                BOOLEAN     NOT NULL DEFAULT TRUE,  -- base p/ transferência interna
    include_in_analysis   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                   JSONB       NOT NULL
);
CREATE INDEX ix_account_fingerprint ON account(fingerprint);

CREATE TABLE balance_snapshot (              -- alimenta "Evolução do saldo"
    account_id   BIGINT      NOT NULL REFERENCES account(id),
    captured_at  TIMESTAMPTZ NOT NULL,
    balance      NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (account_id, captured_at)
);
```

> `balance_snapshot` existe porque a API te dá o saldo **atual**, não a série histórica. Se você não capturar a cada sync, o gráfico de evolução nunca existirá. É barato e irrecuperável depois — capture desde o dia 1.

#### Transações (núcleo)

```sql
CREATE TYPE tx_direction AS ENUM ('IN', 'OUT');
CREATE TYPE tx_status    AS ENUM ('POSTED', 'PENDING');

CREATE TABLE transaction (
    id                    BIGSERIAL PRIMARY KEY,
    account_id            BIGINT      NOT NULL REFERENCES account(id),
    pluggy_transaction_id UUID        NOT NULL UNIQUE,   -- chave natural
    fingerprint           TEXT        NOT NULL,          -- dedup entre reconexões (§4.2)

    description           TEXT        NOT NULL,
    description_norm      TEXT        NOT NULL,          -- lowercase, sem acento/pontuação
    merchant_name         TEXT,

    amount                NUMERIC(14,2) NOT NULL,        -- sinal como veio da Pluggy
    amount_abs            NUMERIC(14,2) NOT NULL,        -- sempre positivo
    direction             tx_direction  NOT NULL,        -- normalizado (§4.1)
    currency_code         CHAR(3)       NOT NULL DEFAULT 'BRL',

    date                  DATE        NOT NULL,          -- data do lançamento
    accrual_date          DATE        NOT NULL,          -- competência (compra); = date p/ conta corrente
    status                tx_status   NOT NULL,

    installment_number    SMALLINT,
    installment_total     SMALLINT,

    pluggy_category       TEXT,
    balance_after         NUMERIC(14,2),

    first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                   JSONB       NOT NULL
);

CREATE UNIQUE INDEX ux_transaction_fingerprint ON transaction(fingerprint);
CREATE INDEX ix_transaction_account_date       ON transaction(account_id, date DESC);
CREATE INDEX ix_transaction_accrual            ON transaction(accrual_date);
CREATE INDEX ix_transaction_status             ON transaction(status) WHERE status = 'PENDING';
CREATE INDEX ix_transaction_desc_norm          ON transaction USING gin (description_norm gin_trgm_ops);
```

> O índice trigram sobre `description_norm` é o que torna viável o matching de regras de orçamento e a detecção de recorrência sem varredura completa.

#### Classificação (suas decisões, separadas dos dados da Pluggy)

```sql
CREATE TABLE category (
    id          SERIAL PRIMARY KEY,
    parent_id   INTEGER REFERENCES category(id),
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL   -- EXPENSE | INCOME | TRANSFER | INVESTMENT
);

CREATE TABLE category_mapping (                -- Pluggy (inglês) -> sua taxonomia (pt-BR)
    pluggy_category TEXT PRIMARY KEY,          -- 'Eating out', 'Groceries', ...
    category_id     INTEGER NOT NULL REFERENCES category(id)
);

CREATE TABLE transaction_classification (
    transaction_id       BIGINT PRIMARY KEY REFERENCES transaction(id),
    category_id          INTEGER REFERENCES category(id),
    is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE,
    is_card_payment      BOOLEAN NOT NULL DEFAULT FALSE,
    exclude_from_analysis BOOLEAN NOT NULL DEFAULT FALSE,
    source               TEXT    NOT NULL,     -- AUTO | MANUAL
    counterpart_tx_id    BIGINT  REFERENCES transaction(id),  -- a "outra perna" da transferência
    note                 TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

> Tabela separada, e não colunas em `transaction`, por um motivo forte: `transaction` é **reescrita pelo sync** (PENDING vira POSTED, valor da parcela muda). Se suas decisões manuais morarem lá, um sync as sobrescreve. Aqui elas são intocáveis pelo worker.

#### Orçamento planejado (gastos fixos e salário)

```sql
CREATE TABLE planned_item (
    id             BIGSERIAL PRIMARY KEY,
    name           TEXT    NOT NULL,          -- 'Aluguel', 'Salário', 'Spotify'
    kind           TEXT    NOT NULL,          -- FIXED_EXPENSE | INCOME | VARIABLE_BUDGET
    category_id    INTEGER REFERENCES category(id),
    expected_amount NUMERIC(14,2) NOT NULL,
    tolerance_pct  NUMERIC(5,2) NOT NULL DEFAULT 10.0,
    expected_day   SMALLINT,                  -- dia do mês esperado (1-31)
    day_tolerance  SMALLINT NOT NULL DEFAULT 5,
    valid_from     DATE    NOT NULL,
    valid_to       DATE,                      -- NULL = vigente (reajuste = novo registro)
    is_active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE planned_item_rule (
    id              BIGSERIAL PRIMARY KEY,
    planned_item_id BIGINT NOT NULL REFERENCES planned_item(id) ON DELETE CASCADE,
    match_type      TEXT   NOT NULL,   -- CONTAINS | REGEX | MERCHANT | AMOUNT_RANGE
    pattern         TEXT,
    amount_min      NUMERIC(14,2),
    amount_max      NUMERIC(14,2),
    account_id      BIGINT REFERENCES account(id),   -- NULL = qualquer conta
    priority        SMALLINT NOT NULL DEFAULT 100
);

CREATE TABLE planned_item_match (
    planned_item_id BIGINT NOT NULL REFERENCES planned_item(id),
    period          CHAR(7) NOT NULL,          -- 'YYYY-MM'
    transaction_id  BIGINT NOT NULL REFERENCES transaction(id),
    matched_amount  NUMERIC(14,2) NOT NULL,
    source          TEXT    NOT NULL,          -- AUTO | MANUAL
    PRIMARY KEY (planned_item_id, period, transaction_id)
);
```

> `valid_from`/`valid_to` em vez de editar `expected_amount`: quando o aluguel reajusta, você abre um novo registro. Sem isso, a comparação planejado × real do ano passado passa a usar o valor de hoje e vira ficção.

#### Investimentos

```sql
CREATE TABLE investment (
    id                   BIGSERIAL PRIMARY KEY,
    connection_id        BIGINT NOT NULL REFERENCES connection(id),
    pluggy_investment_id UUID   NOT NULL UNIQUE,
    name                 TEXT   NOT NULL,
    type                 TEXT,                -- FIXED_INCOME, EQUITY, ...
    subtype              TEXT,                -- CDB, LCI, ...
    issuer               TEXT,
    status               TEXT,                -- ACTIVE | TOTAL_WITHDRAWAL
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    raw                  JSONB  NOT NULL
);

CREATE TABLE investment_snapshot (
    investment_id BIGINT      NOT NULL REFERENCES investment(id),
    captured_at   TIMESTAMPTZ NOT NULL,
    balance       NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (investment_id, captured_at)
);
```

> Na prática, a maioria dos ativos retornados pode estar inativa (em uma conexão real, 13 de 14). Sem o filtro `is_active`, a carteira vira uma lista de CDBs zerados. Mantenha os inativos (histórico de rentabilidade), mas nunca os exiba por padrão.

#### Detecção de recorrência e auditoria

```sql
CREATE TABLE recurrence_candidate (
    id                BIGSERIAL PRIMARY KEY,
    description_norm  TEXT    NOT NULL,
    direction         tx_direction NOT NULL,
    occurrences       SMALLINT NOT NULL,
    avg_amount        NUMERIC(14,2) NOT NULL,
    amount_variance_pct NUMERIC(5,2) NOT NULL,
    avg_interval_days NUMERIC(5,1) NOT NULL,
    regularity_score  NUMERIC(4,3) NOT NULL,   -- 0..1
    last_seen_date    DATE    NOT NULL,
    promoted_to       BIGINT REFERENCES planned_item(id),
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sync_run (
    id             BIGSERIAL PRIMARY KEY,
    kind           TEXT NOT NULL,              -- FULL | INCREMENTAL
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    status         TEXT NOT NULL,              -- RUNNING | SUCCESS | FAILED
    tx_inserted    INTEGER DEFAULT 0,
    tx_updated     INTEGER DEFAULT 0,
    tx_duplicates  INTEGER DEFAULT 0,
    error_message  TEXT
);

CREATE TABLE sync_cursor (
    account_id  BIGINT PRIMARY KEY REFERENCES account(id),
    cursor      TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 4. Decisões críticas de implementação

### 4.1 Normalização de sinal e direção

A Pluggy usa negativo = débito, positivo = crédito. Mas em conta `CREDIT` a semântica se inverte na leitura humana (uma compra "aumenta" a fatura). Resolva **uma vez, na ingestão**:

```
direction = OUT  se (type = BANK  e amount < 0) ou (type = CREDIT e é compra)
direction = IN   se (type = BANK  e amount > 0) ou (type = CREDIT e é estorno/pagamento)
amount_abs = ABS(amount)
```

Toda a camada analítica consulta `direction` + `amount_abs`. Nenhum `CASE WHEN account.type` espalhado por query.

### 4.2 Deduplicação em duas camadas

```
fingerprint = sha256(
    account.fingerprint || '|' ||
    date::text          || '|' ||
    amount_abs::text    || '|' ||
    direction           || '|' ||
    description_norm
)

account.fingerprint = sha256(connector_id || '|' || subtype || '|' || number_masked)
```

Upsert em dois passos:
1. `INSERT ... ON CONFLICT (pluggy_transaction_id) DO UPDATE` — atualiza status, valor, categoria.
2. Se inseriu novo, verificar colisão em `ux_transaction_fingerprint` → é a mesma transação vinda por um item reconectado. Descarte, incremente `tx_duplicates`.

**Risco conhecido:** duas compras idênticas no mesmo dia, mesmo valor, mesmo estabelecimento (dois cafés de R$ 12) colidem falsamente. Mitigação: incluir um contador de ordem por (conta, dia, valor, descrição) no fingerprint.

### 4.3 Transferência interna — o maior risco analítico

Nos dados reais, `Transfers` costuma aparecer como a maior "despesa", e boa parte disso é dinheiro circulando entre as próprias contas do usuário. Regra de casamento no Analysis Engine:

```
Para cada tx OUT em conta própria A:
  procurar tx IN em conta própria B onde
      amount_abs igual
      AND date entre (A.date - 2 dias) e (A.date + 2 dias)
      AND B.id <> A.id
  → marcar ambas is_internal_transfer = TRUE
  → gravar counterpart_tx_id cruzado
```

Complemente com a tag da própria Pluggy (`Same person transfer`) como sinal adicional, nunca como única fonte. E **pagamento de fatura** (`is_card_payment`) segue a mesma exclusão — senão você conta o gasto duas vezes: uma na compra, outra no pagamento.

### 4.4 PENDING vs. POSTED

- `PENDING` **nunca** entra em "quanto gastei este mês".
- `PENDING` alimenta exclusivamente a visão de **compromissos futuros** (a visão de "Despesas Futuras").
- Parcelas: use `installment_number`/`installment_total` para projetar o comprometimento dos próximos meses.
- O sync precisa tratar a transição PENDING → POSTED como **update**, não insert.

### 4.5 Detector de recorrência próprio

A API de Recurring Payments da Pluggy é recurso premium fora do trial. Os critérios estão documentados e são replicáveis:

| Critério | Valor |
|---|---|
| Ocorrências mínimas | 3 |
| Intervalo | ~mensal, 30 ± 5 dias |
| Variância de valor | ≤ 10% |
| Normalização | lowercase, sem caracteres especiais e espaços extras |

Agrupe por `description_norm` + `direction`, calcule intervalo médio e desvio, e gere `regularity_score` = média ponderada entre consistência de intervalo e de valor. Resultado vira `recurrence_candidate`, que você promove manualmente a `planned_item` no frontend. **O detector sugere; você decide.**

### 4.6 Faturas de cartão (Bills) — `credit_card_bill`

A Pluggy expõe `GET /bills`: cada fatura **fechada** de um cartão (conta `type=CREDIT`, `subtype=CREDIT_CARD`), com vencimento, fechamento, valor total, pagamento mínimo e encargos (`financeCharges`). Desde 2026-11-06 o sync grava essas faturas em `credit_card_bill` (migration 0018), lendo todas a cada execução — são uma por mês, e o upsert por `pluggy_bill_id` torna a releitura idempotente.

Até então a decisão era usar só `account.creditData`, e ela se mostrou errada no banco real:

- `account.balance` de uma conta CREDIT é o **limite usado**, não a fatura: inclui parcelas futuras e compras adiadas ("pula compra"). No PicPay, R$ 2.803,00 de limite usado contra R$ 2.517,59 de fatura.
- `creditData.balanceDueDate` ficava defasado: no cartão Free, continuava em 10/10 semanas depois do vencimento.

Por isso `open_credit_card_bill` (§6.2) continua somando `account.balance`, que é a dívida certa para o patrimônio líquido, mas a tela o chama de "limite usado". A fatura que vence vem de `GET /api/bills`, e os compromissos futuros (`/api/metrics/upcoming`) somam as faturas fechadas no mês do vencimento.

Comportamento verificado contra a API em 2026-11-06:

- Valores em reais, não em centavos.
- Só faturas já fechadas. As compras do ciclo corrente aparecem apenas como transações até o fechamento.
- `payments` não diz se a fatura foi paga: o PicPay anexa o pagamento à fatura que ele quitou, o Free à seguinte. Por isso uma fatura conta como compromisso até a data do vencimento, mesmo que já tenha sido paga antes.
- A Pluggy pode trocar o `billId` de provisório para definitivo (changelog de agosto de 2026). Leitura pega uma fatura por cartão por mês de vencimento, a vista mais recentemente.

### 4.7 Webhooks vs. polling — por que o sync é cron, não evento

A Pluggy recomenda webhooks (`item/updated`, `connector/status_updated`, `transactions/created/updated/deleted`, entre outros) como forma de manter dados sincronizados em tempo real, em vez de polling periódico. Este projeto **optou deliberadamente por não usar webhooks**: exigem uma URL HTTPS pública pra receber o POST da Pluggy, o que este ambiente pessoal (Postgres local + K8s sem Ingress público, ver §6.5) não tem hoje. O `CronJob` diário (§7) é o trade-off aceito — dado chega com até 24h de atraso, mas sem precisar expor endpoint nenhum à internet. Se um dia o app ganhar domínio público com HTTPS, webhooks eliminariam esse atraso e substituiriam parte da lógica de `connection_stale` (alerta de conexão da §8) por notificação em tempo real via `connector/status_updated`.

---

## 5. Camada analítica

### Views materializadas (refresh pós-sync)

```sql
-- Versão atual: migration 0019. Crédito no cartão (`is_card_credit`) abate
-- `total_out` em vez de somar em `total_in` (regras do projeto §2, regra 11).
CREATE MATERIALIZED VIEW mv_monthly_cashflow AS
SELECT
    to_char(t.accrual_date, 'YYYY-MM')                                       AS period,
    COALESCE(SUM(t.amount_abs) FILTER (WHERE t.direction = 'IN'
                                         AND NOT t.is_card_credit), 0)       AS total_in,
    COALESCE(SUM(t.amount_abs) FILTER (WHERE t.direction = 'OUT'), 0)
      - COALESCE(SUM(t.amount_abs) FILTER (WHERE t.is_card_credit), 0)       AS total_out,
    SUM(CASE WHEN t.direction = 'IN'  THEN t.amount_abs
             ELSE -t.amount_abs END)                                         AS net
FROM transaction t
JOIN account a ON a.id = t.account_id
LEFT JOIN transaction_classification c ON c.transaction_id = t.id
WHERE t.status = 'POSTED'
  AND a.include_in_analysis
  AND COALESCE(c.is_internal_transfer, FALSE) = FALSE
  AND COALESCE(c.is_card_payment,      FALSE) = FALSE
  AND COALESCE(c.exclude_from_analysis,FALSE) = FALSE
GROUP BY 1;
```

Análogas: `mv_category_month`, `mv_planned_vs_actual`, `mv_networth_daily`.

### Métricas derivadas

| Métrica | Fórmula |
|---|---|
| Taxa de poupança | `net / total_in` |
| Burn rate | média de `total_out` dos últimos 3 meses |
| Runway | `(saldo em contas + investimentos líquidos) / burn rate` |
| Custo fixo mensal | soma dos `planned_item` FIXED_EXPENSE vigentes |
| Margem de segurança | `(renda − custo fixo) / renda` |
| Comprometimento futuro | soma de `PENDING` + parcelas projetadas por mês |
| Patrimônio líquido | contas + investimentos − fatura em aberto |
| Aderência ao orçamento | `matched_amount / expected_amount` por `planned_item` e período |

---

## 6. Camada de aplicação — FastAPI + Angular

### 6.1 Estrutura do repositório

```
repo/
  core/          ← domínio puro, sem HTTP e sem UI
    analysis/      transferência interna, recorrência, métricas
    repository/    acesso ao Postgres (SQLAlchemy)
    models/        entidades e schemas compartilhados
  jobs/          ← CronJobs: sync, recompute, check-consent  → importa core/
  api/           ← FastAPI (routers, auth, dependências)     → importa core/
  web/           ← Angular
  deploy/        ← manifests K8s, nginx.conf
```

**Regra inegociável:** nenhuma regra de negócio dentro de `api/`. Se a taxa de poupança for calculada num router, o job de alertas vai reimplementar e os dois números vão divergir. `api/` traduz HTTP ↔ `core/`, nada mais.

### 6.2 Contrato da API

**Leitura analítica** — servem agregados prontos, nunca dados brutos para o browser somar.

| Método | Rota | Retorno |
|---|---|---|
| GET | `/api/metrics/overview` | saldos por conta, fatura em aberto, patrimônio líquido |
| GET | `/api/metrics/cashflow?from=&to=` | série de `mv_monthly_cashflow` |
| GET | `/api/metrics/categories?period=` | quebra por categoria do período |
| GET | `/api/metrics/planned-vs-actual?period=` | aderência por `planned_item` |
| GET | `/api/metrics/upcoming?months=6` | `PENDING` + parcelas projetadas + faturas fechadas a vencer |
| GET | `/api/metrics/networth?range=12m` | série de patrimônio |
| GET | `/api/accounts` · `/api/investments?active=true` | listagens de apoio |
| GET | `/api/bills?account_id=&limit=12` | faturas fechadas de cartão, mais recentes primeiro (§4.6) |
| GET | `/api/transactions?period=&category=&direction=&cursor=` | listagem paginada por cursor |

**Escrita e classificação**

| Método | Rota | Observação |
|---|---|---|
| PATCH | `/api/transactions/{id}/classification` | categoria, transferência interna, exclusão |
| POST | `/api/transactions/bulk-classify` | reclassificação em lote — o ganho real sobre um dashboard read-only |
| GET/POST/PATCH/DELETE | `/api/planned-items[/{id}]` | com `valid_from`/`valid_to` |
| GET/POST/PATCH/DELETE | `/api/planned-items/{id}/rules[/{ruleId}]` | 1:N com prioridade |
| POST | `/api/planned-items/{id}/rules/preview` | **dry-run**: recebe a regra ainda não salva e devolve quais transações históricas casariam |
| GET | `/api/recurrences` | candidatos do detector |
| POST | `/api/recurrences/{id}/promote` | vira `planned_item` |
| GET | `/api/connections` | status e `consent_expires_at` |
| POST | `/api/sync/run` · GET `/api/sync/runs` | disparo manual e auditoria |

> O endpoint de **preview** é o mais importante da lista e o mais fácil de esquecer. Sem ele você salva uma regex, espera o próximo recompute e descobre que ela casou com 400 transações erradas. Com ele, o formulário mostra o resultado antes de gravar.

### 6.3 Estrutura do front

```
web/src/app/
  core/          ← interceptors HTTP, auth guard, clients gerados do OpenAPI
  shared/        ← componentes de UI, pipes (BRL, período), diretivas
  features/
    overview/      visão geral e patrimônio
    cashflow/      fluxo de caixa e categorias
    transactions/  listagem, filtros, classificação em lote
    budget/        planned-items + rules  ← o núcleo do CRUD
    investments/   carteira (filtrada por is_active)
    settings/      conexões, consentimento, sync manual
```

**Pontos específicos de Angular que valem decidir agora:**

- **Standalone components + signals.** Evite criar `NgModule` novo; a organização por feature com rotas *lazy* já basta.
- **`FormArray` em `budget/`** é a razão de ter escolhido Angular: um `FormGroup` de `planned_item` contendo um `FormArray` de regras, com validação cruzada (`amount_min < amount_max`, `valid_from < valid_to`, prioridade única).
- **Interceptor HTTP** em `core/`: `withCredentials: true`, tratamento centralizado de `401` → rota de login, e de `5xx` → toast de erro.
- **Tipos gerados do OpenAPI.** O FastAPI publica `/openapi.json` automaticamente; gere as interfaces TypeScript no build (openapi-generator ou orval). Contrato tipado ponta a ponta de graça — mudou o schema no Python, o `ng build` quebra.
- **Gráficos:** `ngx-echarts` (mais completo) ou `ng2-charts`. Ambos maduros; escolha um e não misture.
- **Locale:** `registerLocaleData(localePt)` e `LOCALE_ID` = `pt-BR`, senão todo valor sai formatado em padrão americano.

### 6.4 Autenticação

Um usuário só — mantenha simples:

- Login por senha (hash Argon2) contra uma tabela `app_user` de uma linha.
- Sessão em **cookie `httpOnly` + `Secure` + `SameSite=Strict`**, emitido pelo FastAPI. Nada de guardar token em `localStorage`.
- JWT com refresh aqui é complexidade sem benefício: não há múltiplos clientes nem escala horizontal.

### 6.5 Deploy

```
nginx (container)
  ├─ /            → estáticos do  ng build --configuration production
  └─ /api/        → proxy_pass http://fastapi-service:8000/api/
```

Servir front e API **na mesma origem** resolve dois problemas de uma vez: elimina CORS por completo e torna o cookie `SameSite=Strict` viável sem gambiarra. Ingress do K8s aponta para o nginx, e só ele fica exposto.

---

## 7. Ordem de construção sugerida

| Fase | Entrega | Valor |
|---|---|---|
| 1 | Sync + `connection`/`account`/`transaction` + dedup | Você já tem histórico próprio garantido |
| 2 | Classificação + transferência interna + `mv_monthly_cashflow` | Primeiro número **confiável** de gasto mensal |
| 3 | `planned_item` + regras + planejado × real | Vira analisador, não dashboard |
| 4 | Detector de recorrência | Sugestões automáticas de gasto fixo |
| 5 | Investimentos, patrimônio, alertas, previsão | Refinamento |

**Não pule a fase 2.** Um dashboard bonito sobre números que contam transferência interna como despesa é pior do que não ter dashboard — ele te dá confiança em um número errado.

---

## 8. Segurança e operação

- `clientId`/`clientSecret` em **Secret do Kubernetes**, nunca em repositório ou imagem.
- `apiKey` é de curta duração: renove por execução do job, não persista.
- Banco com criptografia em repouso e backup — é o extrato completo da sua vida financeira.
- Se expuser o frontend fora da rede local, autenticação obrigatória. Sem exceção.
- Alerta de consentimento: dispare quando faltarem 30 dias para `consent_expires_at`. Consentimento expirado = sync silenciosamente vazio.
- Alerta de conexão: `connection.status` fora de `UPDATED` por mais de 48h merece notificação. É o primeiro sintoma de uma conexão com problema.
