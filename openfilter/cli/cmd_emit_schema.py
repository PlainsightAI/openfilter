"""``openfilter emit-schema`` — Goldenrod.2 FC-1 / FC-3.

Imports a filter module, locates its ``FilterConfigBase`` subclass, and writes
the emitted JSON Schema to stdout (or ``-o <path>``). This is the build-time
half of the schema-emission contract; FC-3's transport (manifest attestation /
sigstore / ORAS) is layered on top — the CLI's only job is to produce the
artifact.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import logging
import os
import sys
from typing import Iterable

from openfilter.filter_runtime.config import FilterConfigBase

from .common import SCRIPT

logger = logging.getLogger(__name__)
logger.setLevel(int(getattr(logging, (os.getenv("LOG_LEVEL") or "INFO").upper())))


def _candidate_classes(module: object) -> Iterable[type[FilterConfigBase]]:
    for _, attr in inspect.getmembers(module, inspect.isclass):
        if attr is FilterConfigBase:
            continue
        if not issubclass(attr, FilterConfigBase):
            continue
        if attr.__module__ != getattr(module, "__name__", None):
            continue
        yield attr


def _resolve_config_class(spec: str) -> type[FilterConfigBase]:
    """Resolve a module path or ``module:Class`` into a ``FilterConfigBase`` subclass."""
    module_name, _, class_name = spec.partition(":")
    module = importlib.import_module(module_name)

    if class_name:
        cls = getattr(module, class_name, None)
        if cls is None:
            raise SystemExit(f"{spec!r}: {class_name} not found in {module_name}")
        if not (inspect.isclass(cls) and issubclass(cls, FilterConfigBase)):
            raise SystemExit(
                f"{spec!r}: {class_name} is not a FilterConfigBase subclass"
            )
        return cls

    candidates = list(_candidate_classes(module))
    if not candidates:
        raise SystemExit(
            f"{spec!r}: no FilterConfigBase subclass declared in {module_name}. "
            f"Pass module:ClassName to disambiguate or check that the filter is migrated."
        )
    if len(candidates) > 1:
        names = ", ".join(c.__name__ for c in candidates)
        raise SystemExit(
            f"{spec!r}: multiple FilterConfigBase subclasses found ({names}). "
            f"Pass module:ClassName to disambiguate."
        )
    return candidates[0]


def cmd_emit_schema(args: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog=f"{SCRIPT} emit-schema",
        description=(
            "Emit a filter's JSON Schema (draft 2020-12). "
            "MODULE is an importable dotted path; optionally suffix with ':ClassName' "
            "to disambiguate when a module declares more than one config class."
        ),
    )
    parser.add_argument(
        "MODULE",
        help="Importable filter module (e.g. filter_template.filter) "
        "or module:ConfigClass.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output path; '-' (default) writes to stdout.",
    )
    parser.add_argument(
        "--include-managed",
        action="store_true",
        help="Include platform-managed fields in the emitted schema "
        "(default: operator-facing surface only).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (default 2; pass 0 for compact).",
    )

    opts = parser.parse_args(args)
    cls = _resolve_config_class(opts.MODULE)

    schema = cls.emit_schema(include_managed=opts.include_managed)
    schema.setdefault("title", cls.__name__)
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")

    text = json.dumps(schema, indent=opts.indent or None, sort_keys=False)

    if opts.output == "-":
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    else:
        with open(opts.output, "w", encoding="utf-8") as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")
        logger.info("wrote schema for %s to %s", cls.__qualname__, opts.output)
