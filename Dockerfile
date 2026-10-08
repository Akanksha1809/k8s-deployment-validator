# syntax=docker/dockerfile:1

# ---- build stage: produce a wheel ------------------------------------------
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY k8s_validator ./k8s_validator
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# ---- runtime stage ---------------------------------------------------------
FROM python:3.12-slim
LABEL org.opencontainers.image.title="k8s-deployment-validator" \
      org.opencontainers.image.description="Static validation of Kubernetes workload manifests"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels \
    && useradd --system --uid 10001 --no-create-home validator

USER 10001
WORKDIR /manifests

ENTRYPOINT ["k8s-validator"]
