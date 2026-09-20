FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /service
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY computer_daemon ./computer_daemon
EXPOSE 8010
CMD [".venv/bin/uvicorn", "computer_daemon.main:app", "--host", "0.0.0.0", "--port", "8010"]
