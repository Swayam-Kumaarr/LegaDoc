# Production frontend image: build the Vite bundle, serve it with Caddy.
# The dev image (web/Dockerfile) runs the Vite dev server, which must never
# face the internet — it serves source files and accepts any Host header.
# Build context is ./web (see deploy/docker-compose.prod.yml).

FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
