FROM rust:1.94.1-bookworm AS builder

WORKDIR /app

COPY Cargo.toml Cargo.lock* ./
COPY migrations ./migrations
COPY src ./src
COPY tests ./tests

RUN cargo test --lib --tests --no-run \
    && cargo test --lib --tests \
    && cargo build --release --bin doppler-api

FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 doppler \
    && mkdir -p /data \
    && chown -R doppler:doppler /data

WORKDIR /app
COPY --from=builder /app/target/release/doppler-api /usr/local/bin/doppler-api

USER doppler
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

CMD ["doppler-api"]
