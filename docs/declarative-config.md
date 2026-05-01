---
sidebar_label: Declarative Filter Config
title: declarative-filter-config
description: Author filter configuration as typed Python and emit it as JSON Schema for the platform.
---

# Declarative Filter Configuration

`FilterConfigBase` lets a filter declare its config contract in Python
once, and have the platform pick it up at deploy time without
side-loading the filter image. Subclasses get pydantic-settings env-var
sourcing, declarative range / enum / pattern / format constraints, and a
`model_json_schema()` export that the platform ingests for Inspector
rendering, save-time validation, and deployment preflight.

The full design rationale lives in the
[Declarative Filter Configuration Contract — Goldenrod.2 design doc](https://plainsight-ai.atlassian.net/wiki/spaces/ENG/pages/2755919874).
This page is the practical authoring guide.

## When to migrate

Three tiers; pick the one that matches your filter today.

| Tier | What you do | What you get |
|---|---|---|
| 1 | Subclass `FilterConfigBase`, declare typed fields, drop `normalize_config` grammars | Real schema, Inspector renders typed UI, save-time validation, deployment preflight |
| 2 | Subclass `FilterConfigBase` but keep your existing `normalize_config` | Schema export with whatever shape your typed fields cover; grammars stay opaque to the platform |
| 3 | Don't subclass — keep inheriting the legacy `adict`-based `FilterConfig` | Everything keeps working unchanged (deprecated; scheduled for removal at openfilter 1.0) |

Tier 3 is the default for unmigrated filters and remains a working
backcompat shim, but `FilterConfig` is now marked deprecated:
subclassing it raises a `DeprecationWarning` once per subclass and
PEP 702-aware editors flag the symbol. It will be removed at
openfilter 1.0 — migrate to Tier 1 or Tier 2 before then.

Migrate when the visible boundary on your config is wider than your
`normalize_config` rules can describe — i.e. when you'd benefit from
typed UI, validation, or platform preflight more than you'd lose by
giving up the dynamic shape.

## Quick start

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Discriminator, Field

from openfilter.filter_runtime.config import FilterConfigBase, Managed
from openfilter.filter_runtime.formats import VideoSource


class MyFilterConfig(FilterConfigBase):
    # Operator-facing fields
    model_id: str = "facebook/sam3"
    confidence_threshold: float = Field(default=0.5, ge=0, le=1)
    mode: Literal["fast", "accurate"] = "fast"

    # Platform-managed fields (see "The boundary" below)
    sources: list[VideoSource] = Managed([], resolve="orchestrator-generated")
    device: str = Managed("cuda", resolve="device-policy")
```

That's a Tier 1 migration. The platform now knows:

- `confidence_threshold` is a number in `[0, 1]` with default `0.5` — Inspector renders a slider, save-time validation rejects out-of-range values.
- `mode` is one of `"fast" | "accurate"` — Inspector renders a select.
- `sources` and `device` are platform-managed — they're stripped from the operator-facing schema by default and resolved at deployment time.

> **Caveat — defaults aren't validated at import time.** `FilterConfigBase`
> sets `validate_default=False`, so `Field(default=1.5, ge=0, le=1)`
> imports cleanly even though the default violates the constraint; the
> bound only fires when the field is set (e.g. via env var). Cover your
> defaults with an explicit unit test if they have constraints attached.

## Env-var sourcing

`FilterConfigBase` inherits from pydantic-settings's `BaseSettings`. At
runtime, fields are populated from `FILTER_*` env vars; nested fields
use `__` as the delimiter.

```bash
FILTER_MODEL_ID=facebook/sam3
FILTER_CONFIDENCE_THRESHOLD=0.7
FILTER_MODE=accurate
```

For a nested field like `prompting.text_prompt`:

```bash
FILTER_PROMPTING__TEXT_PROMPT="person walking"
```

This is the same `FILTER_*` transport every existing filter already
uses; only the *declaration* changes.

## Tagged unions for mutually-exclusive modes

When a filter has more than one operating mode and config fields differ
between them, model the choice as a discriminated union. The schema
emits `oneOf` plus an OpenAPI `discriminator` so Inspector can render
the right form for each branch.

```python
class TextPrompt(BaseModel):
    prompt_mode: Literal["text"]
    text_prompt: str

class MultiTextPrompt(BaseModel):
    prompt_mode: Literal["multi_text"]
    text_prompts: list[str] = Field(min_length=1)

class Exemplars(BaseModel):
    prompt_mode: Literal["exemplars"]
    exemplars_path: str

Prompting = Annotated[
    Union[TextPrompt, MultiTextPrompt, Exemplars],
    Discriminator("prompt_mode"),
]


class FilterSAM3DetectorConfig(FilterConfigBase):
    prompting: Prompting
    confidence_threshold: float = Field(default=0.5, ge=0, le=1)
```

Set the variant via env vars:

```bash
FILTER_PROMPTING__PROMPT_MODE=text
FILTER_PROMPTING__TEXT_PROMPT="person walking"
```

## Named formats

For values that need richer validation than primitive types — e.g.
URI-shaped sources — use the named-format aliases in
`openfilter.filter_runtime.formats`:

| Alias | Format keyword | Validates |
|---|---|---|
| `OpenfilterSource` | `openfilter-source` | OpenFilter pipeline-internal source URIs |
| `VideoSource` | `video-source` | RTSP / file / HTTP video sources |

```python
from openfilter.filter_runtime.formats import VideoSource

class MyFilterConfig(FilterConfigBase):
    sources: list[VideoSource] = Managed([], resolve="orchestrator-generated")
```

Both ends of the contract validate the same set of strings — Python at
filter runtime, Go on the platform side via the shared spec.

## The boundary: managed vs operator-facing

A filter's config has two audiences. The **operator** picks model
hyperparameters, prompts, output labels — the things they tune for their
use case. The **orchestrator** assigns sources, output topics, devices,
secrets — the things the platform owns.

Mark orchestrator-owned fields with `Managed(...)`:

```python
sources: list[VideoSource] = Managed([], resolve="orchestrator-generated")
device: str               = Managed("cuda", resolve="device-policy")
output_topic: str | None  = Managed(None, resolve="orchestrator-generated")
```

By default, `emit_schema()` strips managed fields from the operator-facing
schema — Inspector won't render them; save-time validation won't
complain about missing values; the platform fills them in at
deployment.

When you need to surface managed fields (e.g. for orchestrator-side
tools), pass `--include-managed`:

```bash
$ openfilter emit-schema my_filter:MyFilterConfig --include-managed
```

The emitted schema annotates each managed field with the FC-2 extension
keywords (`x-openfilter-managed`, `x-openfilter-resolve`).

For fields that the orchestrator may rewrite but should still appear in
the operator-facing schema (e.g. an operator-set value that the platform
templates), use `Resolve(...)` instead — the field stays visible and
gets an `x-openfilter-resolve` marker.

```python
class MyFilterConfig(FilterConfigBase):
    output_path: str = Resolve(
        "/data/{pipeline_id}/{run_id}.jsonl",
        resolve="template-substitution",
    )
```

## Schema emission

Once your config is on `FilterConfigBase`, emit the schema with the
`openfilter emit-schema` CLI (separate ticket;
[FILTER-442](https://plainsight-ai.atlassian.net/browse/FILTER-442)):

```bash
$ openfilter emit-schema my_filter.filter:MyFilterConfig -o schema.json
```

Filter CI calls this at build time and attaches the resulting artifact
to the image manifest as a signed attestation; the platform retrieves
it at deploy time without pulling the image's OCI layers.

## Cheat sheet

| Goal | Pattern |
|---|---|
| Range-bounded number | `Field(default=0.5, ge=0, le=1)` |
| Enum | `Literal["fast", "accurate"]` |
| String pattern | `Field(default="", pattern=r"^[a-z][a-z0-9-]*$")` |
| Optional | `T \| None = None` |
| Nested config struct | `class Sub(BaseModel): ...; sub: Sub` |
| Mutually-exclusive modes | `Annotated[Union[A, B, C], Discriminator("kind")]` |
| Source URI | `list[VideoSource]` (or `list[OpenfilterSource]`) |
| Orchestrator-owned | `Managed(default, resolve="...")` |
| Orchestrator-templated | `Resolve(default, resolve="...")` |

## Related

- Parent epic: [FILTER-440 — Declarative Configuration Contract](https://plainsight-ai.atlassian.net/browse/FILTER-440)
- Build-time CLI: [FILTER-442 — `openfilter emit-schema`](https://plainsight-ai.atlassian.net/browse/FILTER-442)
- Platform-side ingest, validation, Inspector, preflight: tracked on the PLAT board under *Declarative Configuration Validation*
