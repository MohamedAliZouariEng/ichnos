"""Export the OpenAPI contract: python -m ichnos.openapi [output-path]."""

import json
import sys
from pathlib import Path

from ichnos.main import create_app
from ichnos.settings import Settings


def render() -> str:
    """Deterministic JSON: sorted keys, two-space indent, trailing newline."""
    schema = create_app(Settings()).openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        Path(args[0]).write_text(render(), encoding="utf-8")
    else:
        sys.stdout.write(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
