# Stage 1: Build SolidJS frontend
FROM oven/bun:1 AS builder

WORKDIR /build
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . ./
RUN bun run build

# Stage 2: Caddy runtime
FROM caddy:2

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /build/dist /usr/share/caddy/html

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1
