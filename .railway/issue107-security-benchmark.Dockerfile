# exact source branch: feat/107-security-benchmark-v1
FROM python:3.13-bookworm
WORKDIR /app
COPY . .
RUN python --version \
    && python -m pip install --no-cache-dir -q pytest \
    && python -m pytest -q tests/test_security_benchmark_v1.py tests/test_capabilities.py \
    && python benchmarks/security_v1.py --json > /tmp/security-benchmark-v1.json \
    && python -c "import json; p=json.load(open('/tmp/security-benchmark-v1.json')); assert p['schema']=='koschei.security-benchmark/v1'; assert p['claim_policy']['cross_language_claims_enabled'] is False"
CMD ["python", "-c", "print('issue107 security benchmark validation passed')"]
