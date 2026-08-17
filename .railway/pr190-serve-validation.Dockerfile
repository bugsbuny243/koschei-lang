FROM golang:1.24-bookworm AS go
FROM python:3.13-bookworm
COPY --from=go /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"
WORKDIR /app
COPY . .
RUN go version
RUN python -c "import koschei; import koschei.interpreter as i; import koschei.serve_authority_v1 as s; x=i.SystemCaps(); print('SYSTEM_CAPS=',i.SystemCaps); print('SLOTS=',getattr(i.SystemCaps,'__slots__',None)); print('HAS_SERVE=',hasattr(x,'serve')); print('SERVE_INSTALLED=',s._INSTALLED); print('EXEC_GLOBAL=',i.Interpreter._execute_main.__globals__.get('SystemCaps'))"
RUN python -c "import koschei.interpreter as i; from koschei.parser import parse; from koschei.semantic import check,SemanticError; srcs=['fn main(caps: SystemCaps) { let server = caps.serve.allow(\"127.0.0.1:8080\", 5000, 65536, 65536, 5000) }','fn main(caps: SystemCaps) { let connections = 64 let server = caps.serve.allow(\"127.0.0.1:8080\", connections, 65536, 65536, 5000) }']; [(lambda p: check(p))(parse(x)) if False else None for x in []];
for src in srcs:
 try: check(parse(src))
 except SemanticError as e: print('EXPECTED=',e.code)
 print('AFTER_CHECK=',i.SystemCaps,getattr(i.SystemCaps,'__slots__',None),hasattr(i.SystemCaps(),'serve'),i.Interpreter._execute_main.__globals__.get('SystemCaps'))"
RUN python -m unittest -v tests.test_serve_authority_v1 tests.test_serve_authority_loopback_canonical_v1 tests.test_direct_mir_type_integrity_v1 tests.test_fallible_mir_v1 tests.test_data_mir_v1 tests.test_direct_mir_service_surface_v1 tests.test_integer_division_mir_guard_v1 tests.test_mir_native_runtime tests.test_production_reference_system_v1
CMD ["python", "-c", "print('pr190 validation complete')"]
