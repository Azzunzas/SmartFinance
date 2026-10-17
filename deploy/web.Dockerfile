# Build a partir da raiz do repo:
#   docker build -f deploy/web.Dockerfile -t smartfinance-web .
FROM node:24-slim AS build

WORKDIR /web
# npm ci (e não npm install) pra respeitar o package-lock.json — mesma razão do
# requirements.lock no backend: build reproduzível.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# nginx-unprivileged e não a imagem `nginx` padrão: aquela espera iniciar como
# root pra criar /var/cache/nginx e só então baixar privilégio pela diretiva
# `user`. Rodar `USER nginx` nela quebra no boot com "mkdir /var/cache/nginx/
# client_temp failed (13: Permission denied)" — verificado. Esta imagem já vem
# montada pra rodar sem root, escutando em 8080, sem remendo de permissão.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/security-headers.conf /etc/nginx/conf.d/security-headers.conf
COPY --from=build /web/dist/web/browser /usr/share/nginx/html

EXPOSE 8080
