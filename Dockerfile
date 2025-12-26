FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ---- System packages (debug + build essentials) ----
# libatomic1 is required for pyright's node runtime in this image family.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libatomic1 \
    curl \
    jq \
    dnsutils \
    iputils-ping \
    netcat-openbsd \
    procps \
    lsof \
    curl ca-certificates libatomic1 \
  && rm -rf /var/lib/apt/lists/*

# ---- Python deps (runtime) ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Optional: Python dev tools (lint/typecheck/test) ----
# Enable with: docker build --build-arg INSTALL_DEV_TOOLS=1 ...
ARG INSTALL_DEV_TOOLS=0
COPY requirements-dev.txt /app/requirements-dev.txt
RUN if [ "$INSTALL_DEV_TOOLS" = "1" ]; then \
      python -m pip install --no-cache-dir -r /app/requirements-dev.txt ; \
    fi
# ---- App code ----
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
