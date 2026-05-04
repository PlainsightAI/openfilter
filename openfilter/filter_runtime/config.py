"""Declarative filter configuration — Goldenrod.2 FC-1 / FC-2 (schema-emission side).

`FilterConfigBase(BaseSettings)` is the opt-in successor to the legacy
`FilterConfig(adict)` shape. Filters that subclass it get:

    * env-var sourcing via pydantic-settings (FILTER_*, nested via `__`)
    * declarative type + range + enum + pattern + format constraints
    * `emit_schema()` producing JSON Schema draft 2020-12 the platform can
      ingest without pulling the filter image

Managed-vs-operator separation (FC-2) is expressed via the
``x-openfilter-managed`` JSON-schema extension; ``emit_schema()`` excludes
managed fields by default. ``x-openfilter-resolve`` is round-tripped untouched
for downstream consumers (the platform's autofill walker).

Coexists with the legacy ``FilterConfig`` — unmigrated filters keep working
unchanged. See ``openfilter.filter_runtime.formats`` for SDK-owned named
formats.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils import JSONType

__all__ = [
    "FilterConfigBase",
    "Managed",
    "Resolve",
    "ResolveHint",
    "MANAGED_KEY",
    "RESOLVE_KEY",
    "PREFLIGHT_KEY",
]


MANAGED_KEY = "x-openfilter-managed"
RESOLVE_KEY = "x-openfilter-resolve"
PREFLIGHT_KEY = "x-openfilter-preflight"


ResolveHint = Literal[
    "orchestrator-generated",
    "orchestrator-resolved",
    "tenant-provided",
    "secret-ref",
    "agent-env",
    "device-policy",
    "template-substitution",
]


def Managed(
    default: Any = ...,
    *,
    resolve: ResolveHint | None = None,
    preflight: list[dict[str, Any]] | None = None,
    json_schema_extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Field shorthand for platform-managed config keys (FC-2).

    Equivalent to ``Field(..., json_schema_extra={"x-openfilter-managed": True, ...})``.
    Optional ``resolve`` and ``preflight`` populate the matching extension keys
    so the platform's autofill / preflight walkers can dispatch on them.

    ``resolve`` is optional. Pass it when there's a canonical resolution
    category (orchestrator-side autofill, secret manager, agent-env lookup,
    etc.) and the platform should know which dispatcher to use. Omit it when
    the field is purely platform-owned with no further resolution semantics —
    several inherited ``FilterConfigBase`` managed fields (e.g. ``log_path``,
    ``metrics_interval``) are platform-owned plumbing without a canonical
    resolver and intentionally leave ``resolve`` unset.
    """
    extra: dict[str, Any] = dict(json_schema_extra or {})
    extra[MANAGED_KEY] = True
    if resolve is not None:
        extra[RESOLVE_KEY] = resolve
    if preflight is not None:
        extra[PREFLIGHT_KEY] = preflight
    return Field(default, json_schema_extra=extra, **kwargs)


def Resolve(
    default: Any = ...,
    *,
    resolve: ResolveHint,
    preflight: list[dict[str, Any]] | None = None,
    json_schema_extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Field shorthand for operator-facing fields with a resolve hint.

    Unlike ``Managed``, the field stays visible in the emitted schema; the
    hint just tells the platform how to source the value (e.g. ``secret-ref``
    for a tenant secret picker).
    """
    extra: dict[str, Any] = dict(json_schema_extra or {})
    extra[RESOLVE_KEY] = resolve
    if preflight is not None:
        extra[PREFLIGHT_KEY] = preflight
    return Field(default, json_schema_extra=extra, **kwargs)


class FilterConfigBase(BaseSettings):
    """Typed, introspectable base class for filter configuration (FC-1).

    Subclasses declare their pipeline-operator surface as class-body fields.
    Env-var sourcing follows the ``FILTER_*`` convention with ``__`` as the
    nested-field delimiter (e.g. ``FILTER_PROMPTING__PROMPT_MODE=text``).

    Parent fields covering platform-owned plumbing (``sources``, ``outputs``,
    metrics, log path, device) are tagged ``x-openfilter-managed`` so they
    appear only when ``emit_schema(include_managed=True)`` is requested.

    Subclasses may override any inherited managed field — pydantic supports
    field-level inheritance override. ``filter-event-sink`` overriding
    ``sources`` with ``list[OpenfilterSource]`` (from ``formats``) is the
    canonical worked example.
    """

    model_config = SettingsConfigDict(
        env_prefix="FILTER_",
        env_nested_delimiter="__",
        extra="allow",
        case_sensitive=False,
        validate_default=False,
    )

    id: str | None = Managed(None)

    sources: str | list[str] | None = Managed(
        None, resolve="orchestrator-generated"
    )
    sources_balance: bool | None = Managed(None)
    sources_timeout: int | None = Managed(None)
    sources_low_latency: bool | None = Managed(None)

    outputs: str | list[str] | None = Managed(
        None, resolve="orchestrator-generated"
    )
    outputs_balance: bool | None = Managed(None)
    outputs_timeout: int | None = Managed(None)
    outputs_required: str | None = Managed(None)
    outputs_metrics: str | bool | None = Managed(None)
    outputs_filter: bool | None = Managed(None)
    outputs_jpg: bool | None = Managed(None)

    exit_after: float | str | None = None

    environment: str | None = Managed(None, resolve="agent-env")
    log_path: str | Literal[False] | None = Managed(None)

    metrics_interval: float | None = Managed(None)
    extra_metrics: dict[str, JSONType] | list[tuple[str, JSONType]] | None = Managed(None)
    mq_log: str | bool | None = Managed(None)
    mq_msgid_sync: bool | None = Managed(None)

    device: str | int | None = Managed(None, resolve="agent-env")
    metrics_csv_path: str | None = Managed(None)
    metrics_csv_interval: float | None = Managed(None)

    batch_size: int | None = None
    accumulate_timeout_ms: float | None = None

    @classmethod
    def emit_schema(cls, *, include_managed: bool = False) -> dict[str, Any]:
        """Return the filter's JSON Schema (draft 2020-12).

        By default, fields tagged ``x-openfilter-managed: true`` are stripped
        — that's the pipeline-operator surface, what the editor renders.
        Pass ``include_managed=True`` for debugging or for the platform's
        autofill walker, which needs the managed surface to know what it
        owns.
        """
        schema = cls.model_json_schema(mode="validation")
        if not include_managed:
            schema = _strip_managed(schema)
            schema = _prune_orphan_defs(schema)
        schema.setdefault(
            "$schema", "https://json-schema.org/draft/2020-12/schema"
        )
        return schema


def _strip_managed(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove fields tagged ``x-openfilter-managed: true``.

    Walks ``properties`` and any ``$defs`` blocks — nested objects can also
    declare managed fields. Drops matching keys from ``required`` lists.
    Returns a new dict; does not mutate the input.
    """
    if not isinstance(schema, dict):
        return schema

    out: dict[str, Any] = {}
    # Track whether the properties branch already handled `required` so the
    # downstream `elif key == "required"` branch doesn't re-add it. Using a
    # flag rather than `"required" in out` because the properties branch may
    # legitimately decide to omit `required` (every required field was
    # managed), and we must not let the unfiltered original creep back in.
    required_handled = False
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            kept_props: dict[str, Any] = {}
            dropped: set[str] = set()
            for prop_name, prop_schema in value.items():
                if isinstance(prop_schema, dict) and prop_schema.get(MANAGED_KEY) is True:
                    dropped.add(prop_name)
                    continue
                kept_props[prop_name] = _strip_managed(prop_schema)
            out[key] = kept_props
            if dropped and isinstance(schema.get("required"), list):
                required_handled = True
                filtered = [r for r in schema["required"] if r not in dropped]
                if filtered:
                    out["required"] = filtered
                else:
                    # Every required entry was managed — omit the key
                    # entirely rather than emit `required: []`, which some
                    # schema consumers treat as "this object has required
                    # keys" via `if "required" in schema:` checks. Pop in
                    # case a prior `required` branch already populated it
                    # (dict iteration is insertion-ordered, but the original
                    # value would be unfiltered, so we must purge it).
                    out.pop("required", None)
        elif key == "required":
            if required_handled:
                continue
            if isinstance(value, list):
                if value:
                    out[key] = list(value)
                # else: drop empty `required` lists from nested objects too
            else:
                out[key] = value
        elif key == "$defs" and isinstance(value, dict):
            out[key] = {k: _strip_managed(v) for k, v in value.items()}
        elif isinstance(value, dict):
            out[key] = _strip_managed(value)
        elif isinstance(value, list):
            out[key] = [_strip_managed(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out


_DEF_REF_PREFIX = "#/$defs/"


def _collect_def_refs(node: Any, refs: set[str]) -> None:
    """Walk ``node`` collecting every ``#/$defs/<Name>`` ref target into ``refs``.

    Recurses into dicts and lists; skips the top-level ``$defs`` block itself
    (the caller is responsible for excluding it before invoking this) so we
    don't preserve a def just because some other (also-orphaned) def references
    it. Refs reachable only from operator-facing properties survive.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_DEF_REF_PREFIX):
            refs.add(ref[len(_DEF_REF_PREFIX):])
        for k, v in node.items():
            if k == "$ref":
                continue
            _collect_def_refs(v, refs)
    elif isinstance(node, list):
        for item in node:
            _collect_def_refs(item, refs)


def _prune_orphan_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop ``$defs`` entries no longer referenced from anywhere in the schema.

    After ``_strip_managed`` removes managed properties, definitions that were
    only reachable through those properties become orphaned. Walks the schema
    minus ``$defs`` to find the set of live ``#/$defs/<Name>`` targets, then
    iterates to fixed point so a def referenced only by another (now-orphaned)
    def is also collected. Returns a new dict; does not mutate the input.
    """
    defs = schema.get("$defs")
    if not isinstance(defs, dict) or not defs:
        return schema

    body = {k: v for k, v in schema.items() if k != "$defs"}

    live: set[str] = set()
    _collect_def_refs(body, live)

    # Iterate to fixed point: live defs may reference other defs.
    changed = True
    while changed:
        changed = False
        for name in list(live):
            sub = defs.get(name)
            if sub is None:
                continue
            before = len(live)
            _collect_def_refs(sub, live)
            if len(live) != before:
                changed = True

    pruned_defs = {k: v for k, v in defs.items() if k in live}
    out = dict(schema)
    if pruned_defs:
        out["$defs"] = pruned_defs
    else:
        out.pop("$defs", None)
    return out
