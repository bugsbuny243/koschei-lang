# Koschei playground. Build from the repository root:
#   docker build -f server/playground/Dockerfile -t koschei-playground .
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/koschei
COPY pyproject.toml README.md LICENSE ./
COPY koschei ./koschei
COPY native/datajson ./native/datajson
RUN pip install --no-cache-dir . && rm -rf /opt/koschei

COPY server/playground /opt/playground
RUN useradd --system --no-create-home --shell /usr/sbin/nologin playground
USER playground
WORKDIR /opt/playground

EXPOSE 8080
CMD ["python", "app.py"]
