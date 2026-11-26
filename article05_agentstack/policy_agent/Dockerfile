# 本地/独立部署镜像；平台托管的构建与启动方式本文未验证
FROM python:3.13-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PRODUCTION_MODE=true

WORKDIR /app
RUN groupadd --system app \
    && useradd --system --gid app --create-home app \
    && chown app:app /app

# 先装依赖，利用 Docker 层缓存；源码变化时不重复下载
COPY --chown=app:app pyproject.toml uv.lock ./
USER app
RUN uv sync --locked --no-install-project

COPY --chown=app:app . .
RUN uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"
# 本地/独立部署入口；平台托管时启动命令由平台注入（本文未验证）
CMD ["uv", "run", "--no-sync", "server"]