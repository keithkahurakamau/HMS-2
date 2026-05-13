# syntax=docker/dockerfile:1.7
# MediFleet frontend — Vite build → nginx static serve.

# ── Stage 1: build the production bundle ────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /build

# Install deps with a deterministic lockfile install for cache friendliness.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: serve the bundle behind nginx ──────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# SPA + reverse-proxy configuration (see nginx.conf in the repo).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
