FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
ARG EXTRAS=""

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN if [ -n "$EXTRAS" ]; then \
      pip install --no-cache-dir ".[${EXTRAS}]"; \
    else \
      pip install --no-cache-dir .; \
    fi

WORKDIR /workspace

ENTRYPOINT ["aichat"]
CMD ["--help"]
