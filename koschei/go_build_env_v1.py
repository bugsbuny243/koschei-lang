"""The environment `ks build` gives the Go toolchain.

Generated programs import only the Go standard library, so a native build
needs no network and no settings from the caller's Go configuration. The
build is pinned so that nothing outside the compiler's output can change it:

- CGO_ENABLED=0: a static binary, no C toolchain.
- GOFLAGS="" and GOENV=off: flags such as ``-toolexec`` (which runs a program
  around every compiler step) cannot come in from the environment or from the
  user's ``go env -w`` file.
- GOPROXY=off and GOTOOLCHAIN=local: the build never downloads a module or a
  different Go toolchain.
- GOWORK=off: no go.work file around the build directory joins the build.
"""

from __future__ import annotations

import os

PINNED_GO_ENVIRONMENT = {
    "CGO_ENABLED": "0",
    "GOFLAGS": "",
    "GOENV": "off",
    "GOPROXY": "off",
    "GOTOOLCHAIN": "local",
    "GOWORK": "off",
}


def go_build_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(PINNED_GO_ENVIRONMENT)
    return environment
