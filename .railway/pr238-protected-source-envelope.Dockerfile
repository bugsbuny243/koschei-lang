# exact source branch: fix/152-protected-source-envelope
FROM python:3.13-bookworm
WORKDIR /app
COPY . .
RUN python --version \
    && python -m pip install --no-cache-dir -q pytest \
    && python -m pytest -q \
        tests/test_protected_source_envelope_v1.py \
        tests/test_decoy_view_broker_v1.py \
        tests/test_read_authorization_wave2.py \
        tests/test_protected_graph_v1.py
CMD ["python", "-c", "print('pr238 protected source envelope validation passed')"]
