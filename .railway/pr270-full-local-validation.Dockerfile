FROM python:3.13-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSLo /tmp/go.tgz https://go.dev/dl/go1.24.13.linux-amd64.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf /tmp/go.tgz \
    && rm /tmp/go.tgz

ENV PATH="/usr/local/go/bin:${PATH}"
ARG RAILWAY_GIT_COMMIT_SHA

COPY . .

RUN set -eux; \
    python -m pip install --no-cache-dir --upgrade pip pytest; \
    python --version; \
    go version; \
    node --version; \
    git --version; \
    test -n "${RAILWAY_GIT_COMMIT_SHA}"; \
    printf 'RAILWAY SOURCE COMMIT: %s\n' "${RAILWAY_GIT_COMMIT_SHA}"; \
    git init -q .; \
    git add -Af .; \
    TREE="$(git write-tree)"; \
    printf 'VALIDATION SOURCE TREE: %s\n' "$TREE"; \
    PARENT="3248afe14925f1705af65cd892835d7f0184397a"; \
    RAW="$(mktemp)"; \
    printf 'tree %s\nparent %s\nauthor Koschei Validation <validation@local.invalid> 946684800 +0000\ncommitter Koschei Validation <validation@local.invalid> 946684800 +0000\n\nrailway validation checkout' "$TREE" "$PARENT" > "$RAW"; \
    SYNTH="$(git hash-object -t commit -w --stdin < "$RAW")"; \
    rm -f "$RAW"; \
    git update-ref refs/heads/validation "$SYNTH"; \
    git symbolic-ref HEAD refs/heads/validation; \
    git cat-file -p HEAD | grep -Fx "parent $PARENT"; \
    test -z "$(git status --porcelain --untracked-files=normal)"; \
    printf 'VALIDATION LOCAL COMMIT: %s\n' "$SYNTH"; \
    printf 'VALIDATION PR PARENT: %s\n' "$PARENT"; \
    rm -rf /tmp/koschei-pr270-validation; \
    mkdir -p /tmp/koschei-pr270-validation; \
    RC=0; \
    python -m koschei.local_validation_cli \
        --profile full \
        --output /tmp/koschei-pr270-validation/receipt.json \
        --evidence-dir /tmp/koschei-pr270-validation/evidence || RC=$?; \
    printf '\n===== VALIDATION RECEIPT =====\n'; \
    cat /tmp/koschei-pr270-validation/receipt.json || true; \
    printf '\n===== VALIDATION EVIDENCE =====\n'; \
    for FILE in /tmp/koschei-pr270-validation/evidence/*.stdout.log /tmp/koschei-pr270-validation/evidence/*.stderr.log /tmp/koschei-pr270-validation/evidence/*.json; do \
        [ -f "$FILE" ] || continue; \
        printf '\n--- %s ---\n' "$FILE"; \
        cat "$FILE"; \
    done; \
    exit "$RC"

CMD ["python", "-c", "print('pr270 canonical full validation passed')"]
