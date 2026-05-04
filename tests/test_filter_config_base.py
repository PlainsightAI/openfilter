"""Tests for the declarative `FilterConfigBase` (Goldenrod.2 FC-1 / FC-2)."""

from __future__ import annotations

import json
import os
from typing import Annotated, Literal, Union

import pytest
from pydantic import BaseModel, Discriminator, Field, ValidationError

from openfilter.filter_runtime.config import (
    MANAGED_KEY,
    PREFLIGHT_KEY,
    RESOLVE_KEY,
    FilterConfigBase,
    Managed,
    Resolve,
)
from openfilter.filter_runtime.formats import (
    OpenfilterSource,
    VideoSource,
    validate_openfilter_source,
    validate_video_source,
)


# --- FilterConfigBase basics --------------------------------------------------

def _clear_filter_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip any FILTER_* env vars from a test environment."""
    for k in list(os.environ):
        if k.startswith("FILTER_"):
            monkeypatch.delenv(k, raising=False)


class _Simple(FilterConfigBase):
    confidence_threshold: float = Field(default=0.5, ge=0, le=1)
    model_id: str = "facebook/sam3"


def test_emit_schema_strips_managed_parent_fields_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)
    schema = _Simple.emit_schema()
    props = schema["properties"]
    # Operator-facing only: parent's batch_size/accumulate_timeout_ms/exit_after
    # plus the subclass's own fields.
    assert "model_id" in props
    assert "confidence_threshold" in props
    # All managed parent fields stripped
    for managed in (
        "sources",
        "outputs",
        "environment",
        "device",
        "log_path",
        "mq_log",
        "metrics_interval",
        "id",
    ):
        assert managed not in props, f"{managed!r} should be stripped"


def test_emit_schema_include_managed_surfaces_full_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)
    schema = _Simple.emit_schema(include_managed=True)
    props = schema["properties"]
    assert "sources" in props
    assert props["sources"][MANAGED_KEY] is True
    assert props["sources"][RESOLVE_KEY] == "orchestrator-generated"


def test_emit_schema_strips_managed_from_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)

    class C(FilterConfigBase):
        api_token: str = Managed(..., resolve="secret-ref")
        threshold: float = 0.5

    full = C.emit_schema(include_managed=True)
    assert "api_token" in full.get("required", [])

    operator = C.emit_schema()
    assert "api_token" not in operator["properties"]
    assert "api_token" not in operator.get("required", [])


def test_emit_schema_excludes_computed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@computed_field is output-only and must not appear in the input contract."""
    from pydantic import computed_field

    _clear_filter_env(monkeypatch)

    class C(FilterConfigBase):
        a: int = 1

        @computed_field  # type: ignore[misc]
        @property
        def b(self) -> int:
            return self.a + 1

    schema = C.emit_schema()
    assert "b" not in schema.get("properties", {})
    assert "b" not in schema.get("required", [])
    assert "a" in schema["properties"]


def test_env_var_sourcing_with_filter_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)
    monkeypatch.setenv("FILTER_CONFIDENCE_THRESHOLD", "0.7")
    monkeypatch.setenv("FILTER_MODEL_ID", "PekingU/rtdetr_r50vd")

    cfg = _Simple()
    assert cfg.confidence_threshold == 0.7
    assert cfg.model_id == "PekingU/rtdetr_r50vd"


def test_env_var_validation_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)
    monkeypatch.setenv("FILTER_CONFIDENCE_THRESHOLD", "1.5")

    with pytest.raises(ValidationError):
        _Simple()


def test_extra_envvars_tolerated_for_legacy_compat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)
    # Legacy FILTER_* envvars on unmigrated fields shouldn't blow up the
    # migrated subclass — tier-2/tier-3 back-compat per FC-1.
    monkeypatch.setenv("FILTER_LEGACY_RANDOM_FIELD", "whatever")
    monkeypatch.setenv("FILTER_CONFIDENCE_THRESHOLD", "0.3")

    cfg = _Simple()
    assert cfg.confidence_threshold == 0.3


# --- Tagged-union via env_nested_delimiter (sam3 fitness test) ----------------

class _TextPrompt(BaseModel):
    prompt_mode: Literal["text"] = "text"
    text_prompt: str


class _PromptList(BaseModel):
    prompt_mode: Literal["text_list"] = "text_list"
    text_prompts: list[str]


_Prompting = Annotated[
    Union[_TextPrompt, _PromptList], Discriminator("prompt_mode")
]


class _SAM3Like(FilterConfigBase):
    prompting: _Prompting | None = None


def test_tagged_union_via_nested_delimiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)
    monkeypatch.setenv("FILTER_PROMPTING__PROMPT_MODE", "text")
    monkeypatch.setenv("FILTER_PROMPTING__TEXT_PROMPT", "person")

    cfg = _SAM3Like()
    assert cfg.prompting is not None
    assert cfg.prompting.prompt_mode == "text"
    assert cfg.prompting.text_prompt == "person"


def test_tagged_union_emits_oneof_with_discriminator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)
    schema = _SAM3Like.emit_schema()
    prompting = schema["properties"]["prompting"]
    flat = json.dumps(prompting)
    assert "oneOf" in flat or "anyOf" in flat
    assert "prompt_mode" in flat


# --- FC-2 markers -------------------------------------------------------------

def test_managed_helper_sets_extension_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)

    class C(FilterConfigBase):
        url: str = Managed(
            "http://default",
            resolve="orchestrator-resolved",
            preflight=[{"type": "tcp-connect"}],
        )

    schema = C.emit_schema(include_managed=True)
    field = schema["properties"]["url"]
    assert field[MANAGED_KEY] is True
    assert field[RESOLVE_KEY] == "orchestrator-resolved"
    assert field[PREFLIGHT_KEY] == [{"type": "tcp-connect"}]


def test_managed_preserves_caller_supplied_json_schema_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller-supplied json_schema_extra merges with — doesn't replace — managed markers."""
    _clear_filter_env(monkeypatch)

    class C(FilterConfigBase):
        slider: int = Managed(
            0,
            resolve="orchestrator-resolved",
            json_schema_extra={"x-custom-ui-hint": "slider", "x-help": "details"},
        )

    schema = C.emit_schema(include_managed=True)
    field = schema["properties"]["slider"]
    assert field[MANAGED_KEY] is True
    assert field[RESOLVE_KEY] == "orchestrator-resolved"
    assert field["x-custom-ui-hint"] == "slider"
    assert field["x-help"] == "details"


def test_emit_schema_omits_required_when_all_managed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every required field is managed, `required` is omitted entirely
    (not emitted as `required: []`). Some schema consumers gate on
    ``if "required" in schema:`` and treat an empty list as "this object has
    required keys" — emitting nothing is the safe contract."""
    _clear_filter_env(monkeypatch)

    class C(FilterConfigBase):
        # Every required field on this config is managed.
        api_token: str = Managed(..., resolve="secret-ref")
        api_url: str = Managed(..., resolve="orchestrator-resolved")
        # An optional operator-facing field so the schema isn't degenerate.
        threshold: float = 0.5

    full = C.emit_schema(include_managed=True)
    assert set(full.get("required", [])) == {"api_token", "api_url"}

    operator = C.emit_schema()
    # No required keys remain — omit the array entirely.
    assert "required" not in operator, (
        f"expected `required` to be absent, got {operator.get('required')!r}"
    )


def test_emit_schema_sets_dollar_schema_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``emit_schema()`` claims JSON Schema draft 2020-12; the ``$schema``
    keyword should be set so consumers don't have to guess. Pydantic's
    ``model_json_schema()`` doesn't emit ``$schema`` by default — we add it."""
    _clear_filter_env(monkeypatch)

    schema = _Simple.emit_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    schema_full = _Simple.emit_schema(include_managed=True)
    assert schema_full["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_resolve_helper_keeps_field_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)

    class C(FilterConfigBase):
        api_key: str = Resolve(..., resolve="secret-ref")

    schema = C.emit_schema()
    assert "api_key" in schema["properties"]
    assert schema["properties"]["api_key"][RESOLVE_KEY] == "secret-ref"
    assert MANAGED_KEY not in schema["properties"]["api_key"]


def test_child_can_override_managed_parent_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """filter-event-sink-style override: tighten parent `sources` to a typed list."""
    _clear_filter_env(monkeypatch)

    class EventSinkLike(FilterConfigBase):
        sources: list[OpenfilterSource] = Managed(
            [], resolve="orchestrator-generated"
        )

    schema = EventSinkLike.emit_schema(include_managed=True)
    sources = schema["properties"]["sources"]
    assert sources[MANAGED_KEY] is True
    assert sources["items"]["format"] == "openfilter-source"


def test_child_can_surface_managed_parent_field_to_operators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier-1 surface: a child overrides a parent `Managed` field with a plain
    field, promoting it back into the operator-facing schema unmarked."""
    _clear_filter_env(monkeypatch)

    class OperatorPicksDevice(FilterConfigBase):
        # Parent declares `device` as Managed (resolve="agent-env"); child
        # surfaces it as an operator-facing field with a constrained enum.
        device: Literal["cpu", "cuda", "mps"] = "cuda"

    schema = OperatorPicksDevice.emit_schema()
    assert "device" in schema["properties"]
    field = schema["properties"]["device"]
    assert MANAGED_KEY not in field
    assert RESOLVE_KEY not in field


def test_emit_schema_prunes_orphan_defs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After managed-property stripping, ``$defs`` entries reachable only via
    the dropped managed branch must be pruned from the operator schema."""
    _clear_filter_env(monkeypatch)

    class SecretRef(BaseModel):
        provider: Literal["vault", "aws-sm"]
        path: str

    class PublicTuning(BaseModel):
        knob: float = Field(default=0.5, ge=0, le=1)

    class C(FilterConfigBase):
        # Managed nested model — its $defs entry should not appear in the
        # operator-facing schema after stripping.
        api_secret: SecretRef = Managed(
            SecretRef(provider="vault", path="/x"),
            resolve="secret-ref",
        )
        # Non-managed nested model — its $defs entry must survive.
        tuning: PublicTuning = Field(default_factory=PublicTuning)

    full = C.emit_schema(include_managed=True)
    assert "SecretRef" in full.get("$defs", {})
    assert "PublicTuning" in full.get("$defs", {})

    operator = C.emit_schema()
    defs = operator.get("$defs", {})
    assert "SecretRef" not in defs, (
        "SecretRef is reachable only via the stripped api_secret field; "
        "it should be pruned from the operator-facing schema"
    )
    # PublicTuning is still referenced via `tuning`, so it stays.
    assert "PublicTuning" in defs


def test_legacy_filter_config_subclass_emits_deprecation_warning() -> None:
    """The legacy ``adict``-based ``FilterConfig`` is being phased out; subclassing
    it must emit a ``DeprecationWarning`` so unmigrated filters get a runtime nudge."""
    from openfilter.filter_runtime.filter import FilterConfig as LegacyFilterConfig

    with pytest.warns(DeprecationWarning, match="FilterConfigBase"):
        class _LegacySubclass(LegacyFilterConfig):
            pass


def test_emit_schema_prunes_orphan_defs_transitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orphaned ``$defs`` entries must be pruned to a fixed point.

    Constructs a managed-only chain ``A -> B -> C`` where:

    * Top-level managed field has type ``A``.
    * ``A`` has a field of type ``B``.
    * ``B`` has a field of type ``C``.
    * No non-managed field references any of ``A`` / ``B`` / ``C``.

    After ``emit_schema()`` (operator-facing), ALL three nested-model defs
    must be gone. A naive single-pass prune that only walks live refs once
    would still keep ``B`` and ``C`` (because ``A`` references ``B``, and ``B``
    references ``C``) — this exercises the fixed-point loop in
    ``_prune_orphan_defs``.
    """
    _clear_filter_env(monkeypatch)

    class _C(BaseModel):
        leaf: str = "leaf"

    class _B(BaseModel):
        c: _C = Field(default_factory=_C)

    class _A(BaseModel):
        b: _B = Field(default_factory=_B)

    class _Cfg(FilterConfigBase):
        chain: _A = Managed(default_factory=_A)
        # An unrelated operator-facing scalar so the schema isn't degenerate.
        knob: float = Field(default=0.5, ge=0, le=1)

    full = _Cfg.emit_schema(include_managed=True)
    full_defs = full.get("$defs", {})
    assert "_A" in full_defs
    assert "_B" in full_defs
    assert "_C" in full_defs

    operator = _Cfg.emit_schema()
    op_defs = operator.get("$defs", {})
    assert "_A" not in op_defs, "_A is reachable only via the managed chain field"
    assert "_B" not in op_defs, (
        "_B is reachable only through _A (which is itself orphaned); the "
        "fixed-point loop should drop it"
    )
    assert "_C" not in op_defs, (
        "_C is two hops from a non-existent reference root; the "
        "fixed-point loop should drop it"
    )


def test_legacy_filterconfig_silenced_for_sdk_internals() -> None:
    """SDK-internal modules that subclass the legacy ``FilterConfig`` must NOT
    surface a ``DeprecationWarning`` to the user. The suppression filter
    installed in ``openfilter.filter_runtime.filter`` covers
    ``openfilter.filter_runtime.*`` so subclassing from any first-party module
    is silent.

    Pytest manipulates ``warnings.filters`` aggressively (it installs an
    ``always`` rule during test collection so it can record warnings), which
    defeats any in-process verification of the SDK's installed filter. We
    therefore exercise this in a subprocess with ``-W error::DeprecationWarning``
    so the only filter beating the global ``error`` is the SDK's own
    ``ignore`` rule. If the regex doesn't cover an SDK-internal subclassing
    site, the subprocess raises and exits non-zero; if suppression works,
    the subprocess imports cleanly.

    We pick ``openfilter.filter_runtime.filters.util`` because its only
    non-stdlib import beyond core is ``cv2``, which is a hard dependency of
    openfilter, so the test runs in any environment that can import the SDK
    at all.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        """
        import warnings
        # Promote DeprecationWarning to an error globally; the SDK's
        # filterwarnings(...) "ignore" registration during
        # `import openfilter.filter_runtime.filter` is the only thing that
        # should keep the import below from raising.
        warnings.simplefilter("error", DeprecationWarning)

        # SDK-internal subclassing of legacy FilterConfig — must be silent.
        import openfilter.filter_runtime.filters.util  # noqa: F401
        """
    ).strip()

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "SDK-internal subclassing of FilterConfig surfaced a "
        "DeprecationWarning in a subprocess with `simplefilter('error', "
        "DeprecationWarning)` — suppression regex in "
        f"openfilter/filter_runtime/filter.py needs widening.\n\n"
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )


# --- formats: openfilter-source ----------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "tcp://localhost:5550",
        "tcp://192.168.1.10:5552",
        "tcp://localhost:5550;main",
        "tcp://localhost:5550;main>SamGt",
        "ipc:///tmp/sock",
        "ipc:///tmp/sock;main>tgt",
    ],
)
def test_openfilter_source_accepts_valid(value: str) -> None:
    assert validate_openfilter_source(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:5550",  # wrong scheme
        "tcp://",  # missing host
        "rtsp://camera/stream",
        "tcp://localhost:5550;src;tgt",  # bad separator
        "",
    ],
)
def test_openfilter_source_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        validate_openfilter_source(value)


def test_openfilter_source_emits_format_keyword() -> None:
    class C(FilterConfigBase):
        src: OpenfilterSource = "tcp://localhost:5550"

    schema = C.emit_schema()
    assert schema["properties"]["src"]["format"] == "openfilter-source"
    assert schema["properties"]["src"]["type"] == "string"


def test_openfilter_source_validates_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_filter_env(monkeypatch)

    class C(FilterConfigBase):
        src: OpenfilterSource = "tcp://localhost:5550"

    monkeypatch.setenv("FILTER_SRC", "rtsp://wrong/scheme")
    with pytest.raises(ValidationError):
        C()


# --- formats: video-source ----------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "rtsp://camera-42.internal/stream",
        "file:///data/video.mp4",
        "webcam://0",
        "tcp://capture-host:9000",
        "gs://bucket/path/to/object.mp4",
        "http://server/stream",
        "https://server/stream",
    ],
)
def test_video_source_accepts_valid(value: str) -> None:
    assert validate_video_source(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "ftp://server/file",  # unsupported scheme
        "no-scheme",
        "gs://",  # missing bucket
        "rtsp://",  # missing host
        "webcam://",  # missing index
    ],
)
def test_video_source_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        validate_video_source(value)


def test_video_source_emits_format_keyword() -> None:
    class C(FilterConfigBase):
        sources: list[VideoSource] = []

    schema = C.emit_schema()
    items = schema["properties"]["sources"]["items"]
    assert items["format"] == "video-source"
    assert items["type"] == "string"
