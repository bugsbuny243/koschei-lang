# Koschei Forms: built with `ks build` into one static binary.
# CGO_ENABLED=0 keeps it static: without it Go links glibc for its resolver
# and the binary cannot start in the distroless image.
#
# The binary runs as a broker that holds the server socket, the data
# directory and one environment variable, and a worker that runs the program
# under a seccomp allow list with no_new_privs and an empty environment.
# linux/amd64 only: the worker's filter is written for that ABI.

FROM python:3.12-slim AS build
COPY --from=golang:1.24-bookworm /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}" \
    CGO_ENABLED=0
RUN pip install --no-cache-dir koschei-lang==0.24.0
WORKDIR /src
COPY main.ks rules.ks pages.ks csv.ks store.ks LICENSE.md ./
RUN ks build main.ks -o /out/koschei-forms \
    && mkdir -p /out/data/koschei-forms

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/koschei-forms /koschei-forms
COPY --from=build /src/LICENSE.md /LICENSE.md
COPY --from=build --chown=nonroot:nonroot /out/data /data
USER nonroot
EXPOSE 8080
ENTRYPOINT ["/koschei-forms"]
