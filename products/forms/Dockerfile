# Koschei Forms: build with `docker build -t koschei-forms .` in this directory.
# Mount persistent storage at /data (docker run -v ..., or a Railway volume).
FROM python:3.12-slim

RUN pip install --no-cache-dir koschei-lang==0.14.0 \
    && useradd --create-home --uid 10001 forms \
    && mkdir -p /data /app \
    && chown forms:forms /data

WORKDIR /app
COPY main.ks rules.ks pages.ks csv.ks ./

USER forms
EXPOSE 8080

# The server re-opens itself every 4096 requests, so it runs for as long as
# the container does; the step budget only has to be large.
CMD ["ks", "run", "--max-steps", "1000000000000000", "main.ks"]
