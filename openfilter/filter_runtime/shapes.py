"""Shared `frame.data` shape catalog — Goldenrod.2 FC-1 (sibling, FILTER-444).

A library of canonical `frame.data` shapes that filters can ``$ref`` from
their `FilterOutputSchema` instead of negotiating dialects out-of-band. Seeded
from the superset of what existing detector / tracker / OCR / pose filters
emit today; **normative**, not descriptive — filters migrate toward these
shapes via per-filter follow-ups (``filter-sam3-detector`` is the worked
reference under FILTER-444; OCR quad-exposure is one such follow-up).

Shapes are also `FilterOutputSchema` subclasses so they carry a stable
``$id`` and gain ``emit_schema()`` for standalone schema retrieval. Catalog
shapes leave ``__frame_data_key__`` unset — they are nested types, not
``frame.data`` declarations.

Coordinate conventions are per-shape, declared explicitly in each class
docstring and field description:

* `BoundingBox`, `Polygon`, `Mask`, `OCRSpan.quad` — **pixel** coordinates.
* `Keypoint` — **normalized** ``[0, 1]`` (pose convention).

Conventions chosen to match the dominant production pattern. Filters that
emit the alternative coordinate system (e.g. detectors emitting normalized
bboxes) declare their own ``FilterOutputSchema`` rather than ``$ref``-ing
the catalog.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from .output import FilterOutputSchema

__all__ = [
    "BoundingBox",
    "Polygon",
    "Mask",
    "Keypoint",
    "Detection",
    "DetectionSet",
    "Track",
    "TrackSet",
    "Pose",
    "PoseSet",
    "KeypointSet",
    "OCRSpan",
    "OCRSpanSet",
    "ClassificationResult",
    "SHAPE_ID_BASE",
]


SHAPE_ID_BASE = "https://schemas.plainsight.ai/shapes"


def _shape_id(slug: str) -> str:
    return f"{SHAPE_ID_BASE}/{slug}/v1"


# ---------- Geometry primitives ----------


class BoundingBox(FilterOutputSchema):
    """Axis-aligned box in **pixel** coordinates, ``xyxy`` ordering.

    ``(x1, y1)`` is the top-left corner; ``(x2, y2)`` is the bottom-right.
    Ordering is enforced (``x2 >= x1``, ``y2 >= y1``); zero-area boxes are
    permitted (degenerate detections from production NNs do happen) but
    inverted ones are not. Pixel-space because the production detectors
    (``filter-sam3-detector``, ``filter-protege-model``) emit pixel xyxy.
    Detectors that emit normalized or ``cxcywh`` declare a bespoke
    ``FilterOutputSchema`` instead.
    """

    __schema_id__: ClassVar[str] = _shape_id("bounding-box")

    x1: float = Field(description="Left edge, pixel coordinates.")
    y1: float = Field(description="Top edge, pixel coordinates.")
    x2: float = Field(description="Right edge, pixel coordinates.")
    y2: float = Field(description="Bottom edge, pixel coordinates.")

    @model_validator(mode="after")
    def _validate_xyxy_ordering(self) -> "BoundingBox":
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError(
                f"BoundingBox xyxy must be ordered (x2 >= x1, y2 >= y1); "
                f"got x1={self.x1}, y1={self.y1}, x2={self.x2}, y2={self.y2}"
            )
        return self


class Polygon(FilterOutputSchema):
    """Closed polygon as an ordered list of ``(x, y)`` pixel-space vertices.

    Vertex order is implementation-defined; consumers should not rely on
    clockwise vs counter-clockwise. The polygon is implicitly closed (last
    vertex connects to first); ``points`` should not repeat the first vertex
    at the end.
    """

    __schema_id__: ClassVar[str] = _shape_id("polygon")

    points: list[tuple[float, float]] = Field(
        description="Polygon vertices in pixel coordinates, ``[(x, y), ...]``.",
        min_length=3,
    )


class Mask(FilterOutputSchema):
    """Region mask encoded as one or more polygons (COCO-polygon style).

    Multi-polygon ``polygons`` supports masks with holes or disjoint regions.
    ``area`` is optional pixel count for the binary mask the polygons trace.
    Matches the encoding ``filter-sam3-detector`` already emits via
    ``cv2.approxPolyDP`` simplification.
    """

    __schema_id__: ClassVar[str] = _shape_id("mask")

    polygons: list[Polygon] = Field(
        description="Polygons composing the mask region.",
        min_length=1,
    )
    area: int | None = Field(
        default=None,
        description="Optional pixel count of the binary mask.",
        ge=0,
    )


class Keypoint(FilterOutputSchema):
    """Single keypoint in **normalized** ``[0, 1]`` coordinates.

    Normalized because the production pose filter
    (``filter-pose-estimation``) emits 0–1 across both backends (MediaPipe
    and RTMPose). ``z`` is the optional depth/3-D channel (MediaPipe emits
    it, range backend-defined and intentionally unbounded; RTMPose sets
    ``0``). ``visibility`` is the optional MediaPipe visibility-presence
    product; pose backends without it leave it unset. ``confidence`` is
    per-keypoint, mandatory.
    """

    __schema_id__: ClassVar[str] = _shape_id("keypoint")

    x: float = Field(description="Normalized x in [0, 1].", ge=0.0, le=1.0)
    y: float = Field(description="Normalized y in [0, 1].", ge=0.0, le=1.0)
    confidence: float = Field(
        description="Per-keypoint confidence in [0, 1].",
        ge=0.0,
        le=1.0,
    )
    z: float | None = Field(
        default=None,
        description=(
            "Optional depth/3-D channel (MediaPipe). Range backend-defined "
            "(intentionally unbounded). RTMPose sets 0."
        ),
    )
    visibility: float | None = Field(
        default=None,
        description="Optional MediaPipe visibility-presence channel.",
        ge=0.0,
        le=1.0,
    )


# ---------- Detections ----------


class Detection(FilterOutputSchema):
    """A single detected instance.

    Canonical fields chosen to normalize the existing dialect divergence
    (``filter-sam3-detector`` emits ``box``/``bbox``/``score``/``confidence``
    aliases; ``filter-protege-model`` groups by class with shared ``rois``).
    Filters migrating onto the catalog drop the aliasing.

    Open-set detectors (sam3) leave ``label_id`` unset — only the string
    label is meaningful. Closed-set detectors set both.
    """

    __schema_id__: ClassVar[str] = _shape_id("detection")

    bbox: BoundingBox
    score: float = Field(
        description="Confidence score in [0, 1].",
        ge=0.0,
        le=1.0,
    )
    label: str = Field(description="Class label (string; canonical).")
    label_id: int | None = Field(
        default=None,
        description="Optional numeric class id; unset for open-set detectors.",
    )
    mask: Mask | None = Field(
        default=None,
        description="Optional segmentation mask aligned to the bbox.",
    )


class DetectionSet(FilterOutputSchema):
    """A frame's detections."""

    __schema_id__: ClassVar[str] = _shape_id("detection-set")

    items: list[Detection] = Field(default_factory=list)


# ---------- Tracks ----------


class Track(Detection):
    """A tracked detection — `Detection` plus track-lifecycle fields.

    Inherits the box/score/label/mask shape from `Detection`. ``track_id`` is
    mandatory (a track without one is just a detection). ``age`` and
    ``state`` are optional lifecycle hints from the underlying tracker
    (DeepSORT / ByteTrack / etc.); trackers without them leave them unset.
    """

    __schema_id__: ClassVar[str] = _shape_id("track")

    track_id: int = Field(description="Stable cross-frame track identifier.")
    age: int | None = Field(
        default=None,
        description="Optional frames since first observation.",
        ge=0,
    )
    state: Literal["tentative", "confirmed", "lost"] | None = Field(
        default=None,
        description="Optional tracker lifecycle state.",
    )


class TrackSet(FilterOutputSchema):
    """A frame's tracks."""

    __schema_id__: ClassVar[str] = _shape_id("track-set")

    items: list[Track] = Field(default_factory=list)


# ---------- Pose ----------


class Pose(FilterOutputSchema):
    """A single person's pose: an ordered list of `Keypoint`s.

    ``id`` is the person index within the frame; not stable across frames
    (use a tracker for cross-frame identity). ``confidence`` is the
    aggregated person-level score (mean of keypoint confidences in the
    production pose filter). ``skeleton`` names the keypoint convention so
    consumers can interpret keypoint order; ``coco-17`` is the convention
    matching ``filter-pose-estimation``'s normalized output. When
    ``skeleton == "coco-17"`` the keypoint arity is enforced (17 entries) so
    consumers can rely on the index order.
    """

    __schema_id__: ClassVar[str] = _shape_id("pose")

    id: int = Field(
        description="Per-frame person index.",
        ge=0,
    )
    confidence: float = Field(
        description="Aggregated person-level confidence in [0, 1].",
        ge=0.0,
        le=1.0,
    )
    keypoints: list[Keypoint]
    skeleton: Literal["coco-17"] | None = Field(
        default=None,
        description="Keypoint-order convention; consumers infer edges from this.",
    )

    @model_validator(mode="after")
    def _validate_skeleton_arity(self) -> "Pose":
        if self.skeleton == "coco-17" and len(self.keypoints) != 17:
            raise ValueError(
                f"Pose.skeleton='coco-17' requires 17 keypoints, "
                f"got {len(self.keypoints)}"
            )
        return self


class PoseSet(FilterOutputSchema):
    """A frame's poses."""

    __schema_id__: ClassVar[str] = _shape_id("pose-set")

    items: list[Pose] = Field(default_factory=list)


class KeypointSet(FilterOutputSchema):
    """A flat list of `Keypoint`s with no person grouping.

    For filters that emit landmarks without person-level structure (face
    landmarks, hand landmarks, single-person flat output). Use `PoseSet`
    when grouping by person matters.
    """

    __schema_id__: ClassVar[str] = _shape_id("keypoint-set")

    items: list[Keypoint] = Field(default_factory=list)


# ---------- OCR ----------


class OCRSpan(FilterOutputSchema):
    """A single recognized text span.

    ``quad`` is the 4-corner perspective quadrilateral in pixel coordinates,
    matching what EasyOCR's ``readtext(detail=1)`` returns (and what the
    production OCR filter currently discards — a follow-up exposes it).
    Order is typically clockwise from top-left, but consumers should not
    rely on it; ``quad`` is a quadrilateral, not an ordered polyline.
    ``language`` is BCP-47 (e.g. ``"en"``, ``"ja"``); unset when not
    determined per-span.
    """

    __schema_id__: ClassVar[str] = _shape_id("ocr-span")

    text: str = Field(description="Recognized text.")
    confidence: float = Field(
        description="Per-span confidence in [0, 1].",
        ge=0.0,
        le=1.0,
    )
    quad: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ] = Field(
        description=(
            "4-corner perspective quadrilateral in pixel coordinates. "
            "Order is implementation-defined."
        ),
    )
    language: str | None = Field(
        default=None,
        description="Optional BCP-47 language tag.",
    )


class OCRSpanSet(FilterOutputSchema):
    """A frame's OCR spans, in implicit reading order."""

    __schema_id__: ClassVar[str] = _shape_id("ocr-span-set")

    items: list[OCRSpan] = Field(default_factory=list)


# ---------- Classification ----------


class ClassificationResult(FilterOutputSchema):
    """Whole-frame classification output.

    Parallel-arrays shape matching the production ``filter-protege-model``
    convention: ``classes[i]`` pairs with ``confidences[i]``, equal length
    enforced. ``multilabel`` distinguishes single-label (softmax, one
    canonical class) from multi-label (sigmoid, threshold per class) so
    consumers know whether to render top-1 or top-k.
    """

    __schema_id__: ClassVar[str] = _shape_id("classification-result")

    classes: list[str] = Field(default_factory=list)
    confidences: list[float] = Field(default_factory=list)
    multilabel: bool = Field(
        default=False,
        description="True for sigmoid multi-label; False for softmax single-label.",
    )

    @model_validator(mode="after")
    def _validate_parallel_arrays(self) -> "ClassificationResult":
        if len(self.classes) != len(self.confidences):
            raise ValueError(
                f"ClassificationResult.classes and confidences must be "
                f"parallel arrays of equal length; got "
                f"{len(self.classes)} classes and "
                f"{len(self.confidences)} confidences"
            )
        return self
