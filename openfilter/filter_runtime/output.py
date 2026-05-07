"""Declarative filter output-shape declaration — Goldenrod.2 FC-1 (sibling).

`FilterOutputSchema(BaseModel)` is the SDK affordance for declaring what a
filter writes to ``frame.data``. Filters subclass it to describe their
``frame.data`` payload as a build-time JSON Schema (draft 2020-12), the same
way `FilterConfigBase` describes their config surface. Consumers — a shared
visualizer, webvis SSE clients, GT label visualization, downstream filters —
bind against the emitted schema instead of negotiating shapes out-of-band.

Catalog shapes (`openfilter.filter_runtime.shapes`) are also
`FilterOutputSchema` subclasses; filters that publish a bespoke shape stamp
their own ``$id`` (typically ``https://schemas.plainsight.ai/filters/<name>/v1``
for first-party, anything author-controlled for third-party).
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

__all__ = [
    "FilterOutputSchema",
    "FRAME_DATA_KEY",
]


FRAME_DATA_KEY = "x-openfilter-frame-data-key"


class FilterOutputSchema(BaseModel):
    """Typed, introspectable base class for filter output shapes.

    Subclasses declare their ``frame.data`` payload as class-body fields and
    set two class variables:

    * ``__schema_id__`` — the ``$id`` URI for the schema. First-party filters
      use ``https://schemas.plainsight.ai/filters/<name>/v1``; third-party
      filters stamp whatever URI they own. Catalog shapes use
      ``https://schemas.plainsight.ai/shapes/<kebab>/v1``. Optional but
      strongly recommended; without it the emitted schema has no stable
      identity for ``$ref`` resolution. ``__init_subclass__`` propagates the
      value into ``model_config.json_schema_extra`` so pydantic stamps it on
      ``$defs[<Name>]`` when this class is referenced from another schema —
      subclasses only need to set ``__schema_id__``.
    * ``__frame_data_key__`` — the dotted path on ``frame.data`` the schema
      describes. ``"detections"`` means the schema applies to
      ``frame.data["detections"]``; ``"meta.classification"`` means
      ``frame.data["meta"]["classification"]``; ``""`` (empty string) means
      the whole ``frame.data`` namespace. ``None`` (default) means unset —
      catalog shapes leave it ``None`` because they are nested types, not
      standalone ``frame.data`` declarations. Surfaced in the emitted schema
      as the ``x-openfilter-frame-data-key`` extension whenever set (so
      consumers can distinguish "describes whole namespace" from "author
      didn't declare a key").
    """

    __schema_id__: ClassVar[str | None] = None
    __frame_data_key__: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        if "__schema_id__" in cls.__dict__:
            schema_id = cls.__dict__["__schema_id__"]
            if schema_id is not None:
                if not isinstance(schema_id, str) or not schema_id:
                    raise TypeError(
                        f"{cls.__name__}.__schema_id__ must be a non-empty "
                        f"str URI or None, got {schema_id!r}"
                    )
                # Pydantic does not propagate the top-level ``$id`` into
                # ``$defs[<Name>]`` when this class is referenced from another
                # schema; stamping it via ``json_schema_extra`` does. Use
                # ``setdefault`` so an explicit class-level override wins.
                existing = cls.model_config.get("json_schema_extra") or {}
                if isinstance(existing, dict):
                    extra = dict(existing)
                    extra.setdefault("$id", schema_id)
                    cls.model_config["json_schema_extra"] = extra

        if "__frame_data_key__" in cls.__dict__:
            fdk = cls.__dict__["__frame_data_key__"]
            if fdk is not None and not isinstance(fdk, str):
                raise TypeError(
                    f"{cls.__name__}.__frame_data_key__ must be str or None, "
                    f"got {fdk!r}"
                )

    @classmethod
    def emit_schema(cls) -> dict[str, Any]:
        """Return the output schema (JSON Schema draft 2020-12).

        Injects ``$schema``, ``$id`` (when ``__schema_id__`` is set), and the
        ``x-openfilter-frame-data-key`` extension (when ``__frame_data_key__``
        is set — including ``""`` for the whole-namespace case). Pure pydantic
        ``model_json_schema(mode='validation')`` otherwise — output schemas
        have no managed/resolve filtering since they describe data, not
        config.
        """
        schema = cls.model_json_schema(mode="validation")
        schema.setdefault(
            "$schema", "https://json-schema.org/draft/2020-12/schema"
        )
        if cls.__schema_id__ is not None:
            schema["$id"] = cls.__schema_id__
        if cls.__frame_data_key__ is not None:
            schema[FRAME_DATA_KEY] = cls.__frame_data_key__
        return schema
