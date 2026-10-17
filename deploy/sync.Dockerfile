# Build a partir da raiz do repo:
#   docker build -f deploy/sync.Dockerfile -t smartfinance-sync .
FROM python:3.14-slim

WORKDIR /app

# As dependências vêm do lockfile, não da resolução do pyproject: `pip install .`
# com faixas abertas (`sqlalchemy>=2.0,<3.0`) faz um rebuild daqui a seis meses
# trazer bibliotecas diferentes das que passaram nos testes. O lock é gerado num
# venv limpo e validado contra a suíte — ver requirements.lock.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY pyproject.toml ./
COPY core/ core/
COPY jobs/ jobs/
COPY api/ api/

# --no-deps: as dependências já vieram do lock acima; sem isso o pip resolveria
# de novo pelo pyproject e poderia sobrescrever versões travadas.
RUN pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 1000 smartfinance
USER smartfinance

ENTRYPOINT ["python", "-m", "jobs.sync"]
