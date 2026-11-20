# Koschei playground. Build from the repository root:
#   docker build -f server/playground/Dockerfile -t koschei-playground .
FROM python:3.12-slim-bookworm

# Required for per-evaluation mount, PID and network namespace isolation.
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/koschei
COPY pyproject.toml README.md LICENSE ./
COPY koschei ./koschei
COPY native/datajson ./native/datajson
RUN pip install --no-cache-dir . && rm -rf /opt/koschei

COPY server/playground /opt/playground
# Public product site, served at / by the same process; the playground is /play.
COPY commercial/lang-site /opt/site
# Static package registry: index JSON and source archives, served as files.
COPY registry /opt/registry
# The web API executes this fixed Koschei program with bounded numeric input.
# No user-provided source is ever run and the public playground stays disabled.
COPY products/business_web/engine.ks /opt/business/engine.ks
ENV KOSCHEI_SITE_DIR=/opt/site KOSCHEI_REGISTRY_DIR=/opt/registry KOSCHEI_BUSINESS_ENGINE=/opt/business/engine.ks \
    KOSCHEI_CANONICAL_HOST=koschei.dev \
    KOSCHEI_UNTRUSTED_SANDBOX=bwrap \
    KOSCHEI_REQUIRE_CONTAINER_LIMITS=1
RUN useradd --system --no-create-home --shell /usr/sbin/nologin playground
USER playground
WORKDIR /opt/playground

EXPOSE 8080
CMD ["python", "app.py"]
