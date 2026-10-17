# SmartFinance

Painel pessoal de saúde financeira. Consome dados bancários reais via **API Pluggy** (Open Finance regulado, conector MeuPluggy), guarda tudo num Postgres próprio, e cruza **gastos planejados × realizados** — sem depender de planilha ou de re-consultar a Pluggy a cada tela.

Projeto de estudo pessoal, de usuário único. Não é produto, não escala, não tem múltiplos usuários (essa é uma decisão explícita, não uma limitação).

## Documentação — o que ler e quando

| Arquivo | Pra que serve |
|---|---|
| **Este README** | Visão geral rápida, como rodar. Comece aqui. |
| [`docs/arquitetura-app-financas.md`](docs/arquitetura-app-financas.md) | Desenho original: modelo de dados completo, contrato de endpoints, decisões de arquitetura. |
| [`docs/regras-do-projeto.md`](docs/regras-do-projeto.md) | Regras de domínio, convenções de código, decisões de arquitetura e roadmap. |
| [`DESIGN.md`](DESIGN.md) | Direção de design do front: princípios visuais, navegação e conteúdo de cada tela. |

## Stack

| Camada | Tecnologia |
|---|---|
| Domínio + sync | Python 3.14, SQLAlchemy 2.0 (`select()`), Pydantic v2 |
| Banco | PostgreSQL |
| API | FastAPI |
| Front | Angular (standalone components + signals) |
| Gráficos | ECharts via `ngx-echarts` |
| Deploy | Kubernetes |

## Estrutura do repositório

```
core/       domínio puro — ingestão, análise, acesso a Postgres (sem regra de negócio em api/)
api/        FastAPI — routers, schemas Pydantic, autenticação
jobs/       CLI: sync com a Pluggy, motor de análise, checagem de consentimento
alembic/    migrations, lineares, sem branch
web/        front Angular
deploy/     Dockerfile + CronJobs Kubernetes
tests/      pytest, banco Postgres real (sem mocks de banco)
docs/       arquitetura e regras do projeto (ver tabela acima)
```

## Regras de domínio (resumo; lista completa em `docs/regras-do-projeto.md` §2)

O que faz os números do app serem confiáveis, não só bonitos:

1. Compra no cartão conta no mês da **compra**, não da fatura.
2. Pagamento de fatura não é despesa.
3. Transferência entre contas próprias não é despesa (detectada, não assumida).
4. `PENDING` nunca entra em "quanto gastei" — só em compromissos futuros.
5. Nunca `DELETE` em `transaction` — Postgres é o arquivo permanente, a Pluggy só dá 12 meses.
6. Sync roda quantas vezes for preciso sem duplicar nada.

## Como rodar localmente

```bash
docker start smartfinance-postgres        # sobe o Postgres
alembic upgrade head                       # aplica migrations (requer DATABASE_URL)

uvicorn api.main:app --reload --port 8000  # API
cd web && npm start                        # front (proxy automático pra /api)
```

A API exige login desde 2026-08-21 — sem nenhum usuário cadastrado ainda, primeiro `POST /api/auth/register` (username + senha, só funciona uma vez). As variáveis de ambiente estão documentadas em [`.env.example`](.env.example).

## Testes

```bash
pytest
```

Roda contra Postgres real (não mocka banco), cada teste numa transação revertida no final. Cobertura obrigatória (`docs/regras-do-projeto.md` §3): dedup de sync, detecção de transferência interna, detector de recorrência, matching de orçamento.
