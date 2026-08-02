#!/usr/bin/env python3
"""Reference adapter artifact for Koschei Foreign Contract v1.

The compiler does not execute this file yet; it exists to make artifact identity
and the language-neutral contract concrete and testable.
"""

import json
import sys


def main() -> None:
    for line in sys.stdin:
        request = json.loads(line)
        value = request.get("value", "")
        response = {"value": str(value).strip().lower()}
        sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
