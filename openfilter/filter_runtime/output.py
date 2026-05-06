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
      identity for ``$ref`` resolution.
    * ``__frame_data_key__`` — the dotted path on ``frame.data`` the schema
      describes. ``"detections"`` means the schema applies to
      ``frame.data["detections"]``; ``"meta.classification"`` means
      ``frame.data["meta"]["classification"]``; ``""`` (default) means the
      whole ``frame.data`` namespace. Surfaced in the emitted schema as the
      ``x-openfilter-frame-data-key`` extension so consumers know where to
      bind without inspecting filter source.

    Catalog shapes leave ``__frame_data_key__`` empty — they're nested types
    referenced via ``$ref``, not standalone ``frame.data`` declarations.
    """

    __schema_id__: ClassVar[str | None] = None
    __frame_data_key__: ClassVar[str] = ""

    @classmethod
    def emit_schema(cls) -> dict[str, Any]:
        """Return the output schema (JSON Schema draft 2020-12).

        Injects ``$schema``, ``$id`` (when ``__schema_id__`` is set), and the
        ``x-openfilter-frame-data-key`` extension (when ``__frame_data_key__``
        is non-empty). Pure pydantic ``model_json_schema(mode='validation')``
        otherwise — output schemas have no managed/resolve filtering since
        they describe data, not config.
        """
        schema = cls.model_json_schema(mode="validation")
        schema.setdefault(
            "$schema", "https://json-schema.org/draft/2020-12/schema"
        )
        if cls.__schema_id__ is not None:
            schema["$id"] = cls.__schema_id__
        if cls.__frame_data_key__:
            schema[FRAME_DATA_KEY] = cls.__frame_data_key__
        return schema
