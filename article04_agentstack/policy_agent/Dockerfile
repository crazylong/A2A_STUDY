# Agent Stack 平台会用该 Dockerfile 构建 PolicyAgent 镜像
FROM python:3.13-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

ENV UV_LINK_MODE=copy \
    PRODUCTION_MODE=true

ADD . /app
WORKDIR /app

RUN uv sync --no-cache --locked --link-mode copy

ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp

CMD ["uv", "run", "--no-sync", "server"]