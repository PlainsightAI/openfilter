"""Tests for FilterOutputSchema + the shapes catalog (FILTER-444)."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ConfigDict

from openfilter.filter_runtime.output import FRAME_DATA_KEY, FilterOutputSchema
from openfilter.filter_runtime.shapes import (
    SHAPE_ID_BASE,
    BoundingBox,
    ClassificationResult,
    Detection,
    DetectionSet,
    Keypoint,
    KeypointSet,
    Mask,
    OCRSpan,
    OCRSpanSet,
    Polygon,
    Pose,
    PoseSet,
    Track,
    TrackSet,
)


# ---------- FilterOutputSchema base class ----------


class _BareOutput(FilterOutputSchema):
    foo: int
    bar: str = "hello"


class _IdentifiedOutput(FilterOutputSchema):
    __schema_id__: ClassVar[str] = "https://example.com/schemas/identified/v1"
    __frame_data_key__: ClassVar[str] = "meta.identified"

    payload: list[int]


def test_bare_output_emits_draft_2020_12() -> None:
    schema = _BareOutput.emit_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "$id" not in schema  # __schema_id__ unset
    assert FRAME_DATA_KEY not in schema  # __frame_data_key__ unset
    assert "foo" in schema["properties"]


def test_identified_output_stamps_id_and_frame_data_key() -> None:
    schema = _IdentifiedOutput.emit_schema()
    assert schema["$id"] == "https://example.com/schemas/identified/v1"
    assert schema[FRAME_DATA_KEY] == "meta.identified"


def test_init_subclass_auto_stamps_id_into_model_config() -> None:
    """__init_subclass__ propagates __schema_id__ into json_schema_extra so
    pydantic stamps it on $defs[<Name>] entries when the class is referenced
    from another schema. Subclasses should NOT need to set model_config
    manually."""

    class AutoStamped(FilterOutputSchema):
        __schema_id__: ClassVar[str] = "https://example.com/auto/v1"

        thing: int

    extra = AutoStamped.model_config.get("json_schema_extra")
    assert isinstance(extra, dict)
    assert extra["$id"] == "https://example.com/auto/v1"


def test_init_subclass_explicit_model_config_wins() -> None:
    """If the subclass sets json_schema_extra['$id'] explicitly, the
    auto-stamp must not clobber it (setdefault semantics)."""

    class ExplicitOverride(FilterOutputSchema):
        __schema_id__: ClassVar[str] = "https://example.com/from-class-var/v1"
        model_config = ConfigDict(
            json_schema_extra={"$id": "https://example.com/explicit/v1"}
        )

        thing: int

    extra = ExplicitOverride.model_config.get("json_schema_extra")
    assert isinstance(extra, dict)
    assert extra["$id"] == "https://example.com/explicit/v1"


def test_init_subclass_rejects_non_string_schema_id() -> None:
    with pytest.raises(TypeError, match="__schema_id__"):

        class BadId(FilterOutputSchema):
            __schema_id__: ClassVar[int] = 42  # type: ignore[assignment]


def test_init_subclass_rejects_empty_schema_id() -> None:
    with pytest.raises(TypeError, match="__schema_id__"):

        class EmptyId(FilterOutputSchema):
            __schema_id__: ClassVar[str] = ""


def test_init_subclass_rejects_non_string_frame_data_key() -> None:
    with pytest.raises(TypeError, match="__frame_data_key__"):

        class BadFdk(FilterOutputSchema):
            __frame_data_key__: ClassVar[int] = 7  # type: ignore[assignment]


def test_empty_frame_data_key_emits_marker() -> None:
    """``__frame_data_key__ = ""`` is the documented "whole frame.data
    namespace" sentinel. The emitted schema must surface it (not elide it)
    so consumers can distinguish the whole-namespace case from "author
    forgot to declare a key" (in which case the class variable is left
    unset / None and the marker is absent)."""

    class WholeNamespace(FilterOutputSchema):
        __schema_id__: ClassVar[str] = "https://example.com/whole/v1"
        __frame_data_key__: ClassVar[str] = ""

        anything: int

    schema = WholeNamespace.emit_schema()
    assert schema[FRAME_DATA_KEY] == ""


def test_user_filter_can_ref_catalog_shape() -> None:
    """A filter declaring its output via a catalog shape should produce a
    schema where the catalog shape is reachable as a definition."""

    class MyOutput(FilterOutputSchema):
        __schema_id__: ClassVar[str] = "https://schemas.plainsight.ai/filters/foo/v1"
        __frame_data_key__: ClassVar[str] = "detections"

        items: list[Detection]

    schema = MyOutput.emit_schema()
    assert schema["$id"] == "https://schemas.plainsight.ai/filters/foo/v1"
    assert schema[FRAME_DATA_KEY] == "detections"
    # Detection (and its nested BoundingBox / Mask / Polygon) must land in $defs
    defs = schema.get("$defs", {})
    assert "Detection" in defs
    assert "BoundingBox" in defs
    # And the catalog shape's $id must propagate into the $defs entry —
    # this is the load-bearing reason for the __init_subclass__ auto-stamp.
    assert defs["Detection"]["$id"] == Detection.__schema_id__
    assert defs["BoundingBox"]["$id"] == BoundingBox.__schema_id__


def test_user_filter_can_declare_bespoke_shape_with_no_catalog_ref() -> None:
    """A filter that doesn't want to use the catalog must be able to ship
    its own ad-hoc shape."""

    class FilterFooBarOutput(FilterOutputSchema):
        __schema_id__: ClassVar[str] = "https://schemas.plainsight.ai/filters/foo-bar/v1"
        __frame_data_key__: ClassVar[str] = "foo_bar"

        weird_thing: list[dict[str, int]]
        legacy_blob: str
        custom_score: float

    schema = FilterFooBarOutput.emit_schema()
    assert schema["$id"] == "https://schemas.plainsight.ai/filters/foo-bar/v1"
    assert schema[FRAME_DATA_KEY] == "foo_bar"
    # No catalog $refs — no $defs
    assert "$defs" not in schema or not schema["$defs"]


# ---------- Catalog shapes ----------


@pytest.mark.parametrize(
    "cls,slug",
    [
        (BoundingBox, "bounding-box"),
        (Polygon, "polygon"),
        (Mask, "mask"),
        (Keypoint, "keypoint"),
        (Detection, "detection"),
        (DetectionSet, "detection-set"),
        (Track, "track"),
        (TrackSet, "track-set"),
        (Pose, "pose"),
        (PoseSet, "pose-set"),
        (KeypointSet, "keypoint-set"),
        (OCRSpan, "ocr-span"),
        (OCRSpanSet, "ocr-span-set"),
        (ClassificationResult, "classification-result"),
    ],
)
def test_catalog_shape_has_expected_id(cls: type, slug: str) -> None:
    expected = f"{SHAPE_ID_BASE}/{slug}/v1"
    assert cls.__schema_id__ == expected
    schema = cls.emit_schema()
    assert schema["$id"] == expected


def test_catalog_shapes_leave_frame_data_key_unset() -> None:
    """Catalog shapes are nested types, not standalone ``frame.data``
    declarations — the marker must be absent from their emitted schemas."""
    for cls in (BoundingBox, Detection, Pose, ClassificationResult, OCRSpan):
        schema = cls.emit_schema()
        assert FRAME_DATA_KEY not in schema, cls.__name__


def test_bounding_box_pixel_xyxy() -> None:
    bbox = BoundingBox(x1=10, y1=20, x2=100, y2=200)
    assert bbox.x2 > bbox.x1
    schema = BoundingBox.emit_schema()
    for axis in ("x1", "y1", "x2", "y2"):
        assert axis in schema["properties"]
        assert "pixel" in schema["properties"][axis]["description"]


def test_bounding_box_rejects_inverted_xyxy() -> None:
    with pytest.raises(ValueError, match="ordered"):
        BoundingBox(x1=100, y1=100, x2=10, y2=10)
    with pytest.raises(ValueError, match="ordered"):
        BoundingBox(x1=0, y1=10, x2=10, y2=0)


def test_bounding_box_allows_zero_area() -> None:
    """Degenerate (zero-area) boxes are permitted — production NNs do emit
    them and rejecting would force every consumer to filter."""
    BoundingBox(x1=10, y1=10, x2=10, y2=10)


def test_keypoint_normalized_range() -> None:
    Keypoint(x=0.5, y=0.5, confidence=0.9)
    with pytest.raises(ValueError):
        Keypoint(x=1.5, y=0.5, confidence=0.9)


def test_detection_open_set_label_only() -> None:
    """Open-set detectors (sam3) leave label_id unset."""
    Detection(
        bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
        score=0.9,
        label="person",
    )


def test_detection_with_mask() -> None:
    poly = Polygon(points=[(0, 0), (10, 0), (10, 10), (0, 10)])
    mask = Mask(polygons=[poly], area=100)
    Detection(
        bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
        score=0.9,
        label="cat",
        mask=mask,
    )


def test_track_extends_detection() -> None:
    track = Track(
        bbox=BoundingBox(x1=0, y1=0, x2=10, y2=10),
        score=0.9,
        label="car",
        track_id=42,
        state="confirmed",
    )
    assert track.track_id == 42
    # Must inherit Detection fields
    assert track.label == "car"
    assert track.bbox.x2 == 10


def test_ocr_span_quad_is_four_points() -> None:
    OCRSpan(
        text="HELLO",
        confidence=0.95,
        quad=((0, 0), (10, 0), (10, 5), (0, 5)),
    )
    with pytest.raises(ValueError):
        # Three points — invalid
        OCRSpan(
            text="X",
            confidence=0.5,
            quad=((0, 0), (1, 0), (1, 1)),  # type: ignore[arg-type]
        )


def test_pose_carries_skeleton_convention() -> None:
    pose = Pose(
        id=0,
        confidence=0.9,
        keypoints=[
            Keypoint(x=0.5, y=0.5, confidence=0.9) for _ in range(17)
        ],
        skeleton="coco-17",
    )
    assert pose.skeleton == "coco-17"
    assert len(pose.keypoints) == 17


def test_pose_without_skeleton_skips_arity_check() -> None:
    """When skeleton is unset, keypoint count is not constrained — filters
    emitting non-coco conventions or partial keypoints are still valid."""
    Pose(
        id=0,
        confidence=0.9,
        keypoints=[Keypoint(x=0.5, y=0.5, confidence=0.9)],
    )


def test_pose_coco17_rejects_wrong_arity() -> None:
    with pytest.raises(ValueError, match="17 keypoints"):
        Pose(
            id=0,
            confidence=0.9,
            keypoints=[Keypoint(x=0.5, y=0.5, confidence=0.9)],
            skeleton="coco-17",
        )


def test_classification_result_supports_multilabel() -> None:
    single = ClassificationResult(classes=["dog"], confidences=[0.9])
    assert single.multilabel is False
    multi = ClassificationResult(
        classes=["dog", "leash"],
        confidences=[0.9, 0.7],
        multilabel=True,
    )
    assert multi.multilabel is True


def test_classification_result_rejects_parallel_array_mismatch() -> None:
    with pytest.raises(ValueError, match="parallel arrays"):
        ClassificationResult(classes=["dog", "cat"], confidences=[0.9])
    with pytest.raises(ValueError, match="parallel arrays"):
        ClassificationResult(classes=["dog"], confidences=[0.9, 0.1])
