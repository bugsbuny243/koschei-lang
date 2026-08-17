# exact source base: d00ad6b3fa2fbffb5f108d6bd5f23c10461269df
# final exact service trigger
FROM python:3.13-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/* \
    && curl -fsSLo /tmp/go.tgz https://go.dev/dl/go1.24.13.linux-amd64.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf /tmp/go.tgz \
    && rm /tmp/go.tgz
ENV PATH="/usr/local/go/bin:${PATH}"
COPY . .
RUN go version && python --version && python -m unittest -v \
    tests.test_bounded_persistence_v1 \
    tests.test_persistence_concurrency_v1 \
    tests.test_persistence_exact_object_integrity_v1 \
    tests.test_persistence_parent_integrity_v1 \
    tests.test_persistence_native_authority_alignment_v1 \
    tests.test_persistence_native_exact_object_integrity_v1 \
    tests.test_persistence_native_go_v1 \
    tests.test_persistence_native_parent_integrity_v1 \
    tests.test_production_reference_http_ingress_v1 \
    tests.test_production_reference_system_v1 \
    tests.test_direct_mir_service_surface_v1
CMD ["python", "-c", "print('pr194 native persistence validation passed')"]
