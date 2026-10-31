# syntax=docker/dockerfile:1
# Where Councils Stand: the website, its API and the data tools in one image. The data lives in the /data volume.

# The pages (Vite, TypeScript, React)
FROM node:22.23.4-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM python:3.12.15-slim
# security fixes published since the base image was built
RUN apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.32
# the site runs as its own user, not root (the same number as the charity's other sites)
RUN groupadd --system --gid 10001 councils \
 && useradd --system --uid 10001 --gid councils --home-dir /home/councils --create-home councils \
 && mkdir -p /data /backups && chown councils:councils /data /backups
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY config ./config
COPY data_static ./data_static
COPY --from=web /web/dist ./web/dist
RUN uv sync --frozen --no-dev --extra embed --compile-bytecode
ENV COUNCILS_DATA_DIR=/data \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
USER councils
EXPOSE 8000
CMD ["councils", "serve", "--host", "0.0.0.0", "--port", "8000", "--behind-proxy"]
