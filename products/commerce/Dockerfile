# Build from repository root:
# docker build -f products/commerce/Dockerfile -t koschei-commerce .
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/koschei
COPY pyproject.toml README.md LICENSE ./
COPY koschei ./koschei
COPY native/datajson ./native/datajson
RUN pip install --no-cache-dir . && rm -rf /opt/koschei
COPY products/commerce /opt/commerce
RUN groupadd --system commerce \
    && useradd --system --gid commerce --no-create-home --shell /usr/sbin/nologin commerce \
    && mkdir -p /data \
    && chown commerce:commerce /data
USER commerce
WORKDIR /opt/commerce
# /data is mounted using the Railway service volume configuration; no Docker VOLUME.
ENV COMMERCE_DB_PATH=/data/commerce.db COMMERCE_ACCEPT_ORDERS=0
EXPOSE 8080
CMD ["python","server.py"]
