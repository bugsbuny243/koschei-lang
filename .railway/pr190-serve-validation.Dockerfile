FROM golang:1.24-bookworm AS go
FROM python:3.13-bookworm
COPY --from=go /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"
WORKDIR /app
COPY . .
RUN go version
RUN python -c "import koschei.interpreter as i; from koschei.parser import parse; from koschei.semantic import check; src='fn accept(server: ServeCaps) {} fn main(caps: SystemCaps) { let server = caps.serve.allow(\"127.0.0.1:8080\", 64, 65536, 65536, 5000) accept(server) }'; print('BEFORE',i.SystemCaps,getattr(i.SystemCaps,'__slots__',None),hasattr(i.SystemCaps(),'serve')); p=parse(src); check(p); print('AFTER_CHECK',i.SystemCaps,getattr(i.SystemCaps,'__slots__',None),hasattr(i.SystemCaps(),'serve')); print('EXEC_GLOBAL',i.Interpreter._execute_main.__globals__.get('SystemCaps'))"
RUN python -m unittest -v tests.test_serve_authority_v1 tests.test_serve_authority_loopback_canonical_v1 tests.test_direct_mir_type_integrity_v1 tests.test_fallible_mir_v1 tests.test_data_mir_v1 tests.test_direct_mir_service_surface_v1 tests.test_integer_division_mir_guard_v1 tests.test_mir_native_runtime tests.test_production_reference_system_v1
CMD ["python", "-c", "print('pr190 validation complete')"]
