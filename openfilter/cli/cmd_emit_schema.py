"""``openfilter emit-schema`` — Goldenrod.2 FC-1 / FC-3.

Imports a filter module, locates its ``FilterConfigBase`` (config) or
``FilterOutputSchema`` (output) subclass, and writes the emitted JSON Schema
to stdout (or ``-o <path>``). This is the build-time half of the
schema-emission contract; FC-3's transport (sibling OCI artifact + manifest
label) is layered on top in the shared filter-release workflows — the CLI's
only job is to produce the artifact.

The default ``--kind config`` preserves the FILTER-442 contract;
``--kind output`` emits the FILTER-444 ``frame.data`` shape declaration.
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
from openfilter.filter_runtime.output import FilterOutputSchema

from .common import SCRIPT

logger = logging.getLogger(__name__)
logger.setLevel(int(getattr(logging, (os.getenv("LOG_LEVEL") or "INFO").upper())))


_BASES: dict[str, type] = {
    "config": FilterConfigBase,
    "output": FilterOutputSchema,
}


def _candidate_classes(module: object, base: type) -> Iterable[type]:
    for _, attr in inspect.getmembers(module, inspect.isclass):
        if attr is base:
            continue
        if not issubclass(attr, base):
            continue
        if attr.__module__ != getattr(module, "__name__", None):
            continue
        yield attr


def _resolve_class(spec: str, base: type) -> type:
    """Resolve a module path or ``module:Class`` into a ``base`` subclass."""
    module_name, _, class_name = spec.partition(":")
    module = importlib.import_module(module_name)

    if class_name:
        cls = getattr(module, class_name, None)
        if cls is None:
            raise SystemExit(f"{spec!r}: {class_name} not found in {module_name}")
        if not (inspect.isclass(cls) and issubclass(cls, base)):
            raise SystemExit(
                f"{spec!r}: {class_name} is not a {base.__name__} subclass"
            )
        return cls

    candidates = list(_candidate_classes(module, base))
    if not candidates:
        raise SystemExit(
            f"{spec!r}: no {base.__name__} subclass declared in {module_name}. "
            f"Pass module:ClassName to disambiguate or check that the filter is migrated."
        )
    if len(candidates) == 1:
        return candidates[0]

    # Filter authors commonly co-locate a top-level FilterOutputSchema
    # subclass with one or more bespoke nested helpers in the same file. The
    # top-level one anchors a frame.data path (non-None __frame_data_key__);
    # helpers leave it None. When exactly one candidate is anchored, prefer it.
    if base is FilterOutputSchema:
        anchored = [
            c for c in candidates
            if getattr(c, "__frame_data_key__", None) is not None
        ]
        if len(anchored) == 1:
            return anchored[0]

    names = ", ".join(c.__name__ for c in candidates)
    raise SystemExit(
        f"{spec!r}: multiple {base.__name__} subclasses found ({names}). "
        f"Pass module:ClassName to disambiguate."
    )


def cmd_emit_schema(args: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog=f"{SCRIPT} emit-schema",
        description=(
            "Emit a filter's JSON Schema (draft 2020-12). "
            "MODULE is an importable dotted path; optionally suffix with ':ClassName' "
            "to disambiguate when a module declares more than one matching class."
        ),
    )
    parser.add_argument(
        "MODULE",
        help="Importable filter module (e.g. filter_template.filter) "
        "or module:Class.",
    )
    parser.add_argument(
        "--kind",
        choices=["config", "output"],
        default="config",
        help="Schema kind: 'config' (FilterConfigBase, default) or 'output' "
        "(FilterOutputSchema, FILTER-444 frame.data declaration).",
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
        "(--kind config only; default: operator-facing surface only).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (default 2; pass 0 for compact).",
    )

    opts = parser.parse_args(args)

    if opts.include_managed and opts.kind != "config":
        raise SystemExit("--include-managed is only valid with --kind config.")

    base = _BASES[opts.kind]
    cls = _resolve_class(opts.MODULE, base)

    if opts.kind == "config":
        schema = cls.emit_schema(include_managed=opts.include_managed)
    else:
        schema = cls.emit_schema()

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
        logger.info(
            "wrote %s schema for %s to %s",
            opts.kind,
            cls.__qualname__,
            opts.output,
        )
