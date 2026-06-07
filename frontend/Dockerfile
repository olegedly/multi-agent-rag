# Stage 1: Build SolidJS frontend
FROM oven/bun:1 AS frontend-builder

WORKDIR /build
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . ./
RUN bun run build

# Stage 2: Build Caddy with rate-limit plugin
FROM caddy:2-builder AS caddy-builder

RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    xcaddy build \
    --with github.com/mholt/caddy-ratelimit

# Stage 3: Caddy runtime with plugin
FROM caddy:2

COPY --from=caddy-builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend-builder /build/dist /usr/share/caddy/html

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1
