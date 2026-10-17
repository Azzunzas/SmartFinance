# Build a partir da raiz do repo:
#   docker build -f deploy/api.Dockerfile -t smartfinance-api .
FROM python:3.14-slim

WORKDIR /app

# Dependências do lockfile, não da resolução aberta do pyproject — mesmo
# raciocínio do sync.Dockerfile. Copiado antes do código pra essa camada ficar
# em cache enquanto só o código muda.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY pyproject.toml ./
COPY core/ core/
COPY jobs/ jobs/
COPY api/ api/
COPY alembic/ alembic/
COPY alembic.ini ./

RUN pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 1000 smartfinance
USER smartfinance

EXPOSE 8000

# Sem --reload e com um worker só. Desde 2026-08-24 isso é escolha, não
# requisito: `claim_manual_sync` passou a usar advisory lock do Postgres
# (core/locks.py), que vale entre processos, então mais de um worker (ou mais de
# uma réplica) não faz o 409 de "sync já em andamento" deixar de segurar. Antes
# era um threading.Lock, por processo, e um worker era obrigatório. Continua em
# 1 porque é um usuário só e não há gargalo medido (docs/regras-do-projeto.md §4). Ver
# deploy/k8s/api.yaml, que fixa replicas: 1 pelo mesmo motivo.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
