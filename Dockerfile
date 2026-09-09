FROM golang:1.24-bookworm AS go-toolchain

FROM python:3.12-bookworm AS builder

COPY --from=go-toolchain /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        openssl \
        patchelf \
        zip \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir nuitka ordered-set zstandard

WORKDIR /src
COPY . .

# Railway exposes this for GitHub-backed deployments. Fail closed rather than
# minting a release manifest that cannot be traced to the deployed source.
ARG RAILWAY_GIT_COMMIT_SHA

RUN set -eux; \
    test -n "${RAILWAY_GIT_COMMIT_SHA}"; \
    python tools/build_solohost_binary_v1.py --mode onefile --output out/build; \
    BIN="$(find out/build -type f -name ks -perm -111 | head -n1)"; \
    test -n "$BIN"; \
    python tools/smoke_solohost_binary_v1.py "$BIN" --require-native-build --receipt out/smoke.json; \
    VERSION="$("$BIN" version --json | python -c 'import json,sys; print(json.load(sys.stdin)["version"])')"; \
    test -n "$VERSION"; \
    python tools/assemble_solohost_staging_v1.py \
      --binary "$BIN" \
      --output out/release \
      --version "$VERSION" \
      --platform linux-x86_64 \
      --source-commit "${RAILWAY_GIT_COMMIT_SHA}" \
      --smoke-receipt out/smoke.json; \
    openssl genpkey -algorithm ED25519 -out /tmp/testnet-ed25519.pem; \
    python tools/sign_solohost_release_v1.py out/release --private-key /tmp/testnet-ed25519.pem; \
    openssl pkey -in /tmp/testnet-ed25519.pem -pubout -out out/release/koschei-testnet-release-public.pem; \
    rm -f /tmp/testnet-ed25519.pem; \
    printf '%s\n' 'TESTNET RELEASE: ephemeral build signing identity; not a production trust anchor.' > out/release/TESTNET-NOTICE.txt; \
    cp out/smoke.json out/release/koschei-solohost-smoke-receipt.json; \
    cp out/build/koschei-solohost-build-receipt.json out/release/ 2>/dev/null || true; \
    mkdir -p out/publish; \
    (cd out && zip -9 -r "publish/koschei-lang-${VERSION}-testnet-linux-x86_64.zip" release); \
    sha256sum out/publish/koschei-lang-*-testnet-linux-x86_64.zip > out/publish/package.sha256; \
    find out/publish -maxdepth 1 -type f -print

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /srv
COPY --from=builder /src/out/publish/ /srv/

EXPOSE 8080
CMD ["sh", "-c", "python -m http.server ${PORT:-8080} --bind 0.0.0.0 --directory /srv"]
