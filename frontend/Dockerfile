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
