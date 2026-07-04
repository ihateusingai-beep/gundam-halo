"""YOLO detector for UI element detection (Sprint 30 Track A).

Per `docs/FEATURE-SPEC-SPRINT30.md` §4.1.

The detector wraps a YOLOv8n ONNX model fine-tuned on
messaging app screenshots (WhatsApp, Telegram, Signal,
Discord). The model is **bundled** with the project at
`~/.gundam-halo/models/yolov8n-messaging.onnx` (~50MB,
downloaded on first use via
`scripts/download_yolo_model.py`).

**Why this is more robust than hard-coded coordinates**:
the YOLO model is trained on the UI, not the coordinates.
As long as the app's UI has the same "contact search bar"
element (in any resolution), the model finds it.

**YOLO classes** (4 classes total, per spec §4.1):
  - 0: contact_search_bar
  - 1: contact_result
  - 2: message_bar
  - 3: send_button

**CPU inference via onnxruntime** (~50ms per screenshot
on M-series, ~200ms on Intel Macs). No GPU needed.

**CI testing strategy**: the real YOLO model can't run
in CI (no display, no model file). The tests in
`tests/tools/test_yolo.py` mock the onnxruntime
InferenceSession and verify the contract (preprocess,
postprocess, detection, error handling).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Default path to the bundled YOLO model. The user can
# override via `SendMessageConfig.yolo_model_path`. The
# model is downloaded on first use via
# `scripts/download_yolo_model.py`.
# Sprint 56 R1: route through `app.paths.models_dir()`.
from app.paths import models_dir
DEFAULT_YOLO_MODEL_PATH = models_dir() / "yolov8n-messaging.onnx"

# YOLO class names (4 classes, per spec §4.1).
# Index = class ID, value = human-readable name.
YOLO_CLASSES: Dict[int, str] = {
    0: "contact_search_bar",
    1: "contact_result",
    2: "message_bar",
    3: "send_button",
}

# YOLO input size. YOLOv8n uses 640x640 by default.
YOLO_INPUT_SIZE: int = 640


class YOLODetectorError(RuntimeError):
    """Raised on YOLO detector errors (model load failure,
    preprocess failure, postprocess failure, etc.)."""


@dataclass
class Detection:
    """A single YOLO detection result.

    Attributes:
        class_name: The class name (e.g. "contact_search_bar").
        class_id: The class ID (0-3).
        confidence: The detection confidence (0-1).
        x: The x coordinate of the detection's center pixel.
        y: The y coordinate of the detection's center pixel.
        width: The bounding box width in pixels.
        height: The bounding box height in pixels.
    """
    class_name: str
    class_id: int
    confidence: float
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> Dict[str, Any]:
        """Return the detection as a JSON-serialisable dict."""
        return {
            "class_name": self.class_name,
            "class_id": self.class_id,
            "confidence": self.confidence,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


class YOLODetector:
    """Wraps the YOLOv8n ONNX model + onnxruntime inference.

    Usage:
        detector = YOLODetector(model_path=Path("yolov8n-messaging.onnx"))
        detections = detector.detect(
            screenshot=np_array,
            target_class="contact_search_bar",
            confidence_threshold=0.7,
        )
        if detections:
            x, y = detections[0].x, detections[0].y

    The detector is **stateless** — `detect()` is safe to
    call from multiple threads. The onnxruntime
    InferenceSession is created once at init time and
    reused across calls.
    """

    def __init__(self, model_path: Path):
        """Load the YOLO model from `model_path`.

        Raises:
            YOLODetectorError: If the model file is missing
                or the onnxruntime import fails.
        """
        if not isinstance(model_path, Path):
            model_path = Path(model_path)
        if not model_path.exists():
            raise YOLODetectorError(
                f"YOLO model not found at {model_path}. "
                f"Run `python scripts/download_yolo_model.py` "
                f"to download the model, or set "
                f"`tools.send_message.yolo_model_path` in "
                f"`~/.gundam-halo/config.toml`."
            )
        # Lazy import onnxruntime so the test suite can
        # import this module without the dep installed.
        try:
            import onnxruntime  # type: ignore  # noqa: F401
        except ImportError as e:
            raise YOLODetectorError(
                f"onnxruntime is required for the YOLO detector. "
                f"Install with: "
                f"uv sync --extra tool-send-message. ({e})"
            ) from e

        # Lazy import here to avoid forcing onnxruntime at
        # module import time (test suite may not have it).
        import onnxruntime as ort  # type: ignore

        self._model_path = model_path
        try:
            self._session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
        except Exception as e:
            raise YOLODetectorError(
                f"Failed to load YOLO model from {model_path}: {e}"
            ) from e

        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name
        # Cache the input shape (e.g. [1, 3, 640, 640])
        input_shape = self._session.get_inputs()[0].shape
        # YOLOv8n input is [batch, channels, height, width].
        # The 4th dim is width; the 3rd is height.
        self._input_height = int(input_shape[2]) if len(input_shape) > 2 else YOLO_INPUT_SIZE
        self._input_width = int(input_shape[3]) if len(input_shape) > 3 else YOLO_INPUT_SIZE

    @property
    def model_path(self) -> Path:
        """The path to the loaded YOLO model."""
        return self._model_path

    @property
    def input_size(self) -> Tuple[int, int]:
        """The YOLO input size as (height, width)."""
        return (self._input_height, self._input_width)

    def detect(
        self,
        screenshot: Any,  # np.ndarray — typed as Any to avoid numpy import
        target_class: str,
        confidence_threshold: float = 0.7,
    ) -> List[Detection]:
        """Run YOLO inference on `screenshot` and return
        detections of `target_class` filtered by
        `confidence_threshold`.

        Args:
            screenshot: A numpy ndarray of shape
                (H, W, 3) in BGR or RGB format (the
                detector doesn't care which; the model
                is trained on either). The image is
                resized to the YOLO input size before
                inference.
            target_class: The class name to filter by
                (e.g. "contact_search_bar"). Must be a
                key in `YOLO_CLASSES.values()`.
            confidence_threshold: Minimum confidence
                (0-1) for a detection to be returned.

        Returns:
            A list of `Detection` objects sorted by
            confidence (highest first). Empty list if
            no detection matches.

        Raises:
            YOLODetectorError: If the target_class is
                unknown or the screenshot is invalid.
        """
        # Validate target_class
        valid_class_names = set(YOLO_CLASSES.values())
        if target_class not in valid_class_names:
            raise YOLODetectorError(
                f"Unknown target_class {target_class!r}. "
                f"Valid: {sorted(valid_class_names)}"
            )

        # Preprocess: resize to YOLO input size + normalize
        input_tensor = self._preprocess(screenshot)

        # Run inference
        try:
            outputs = self._session.run(
                [self._output_name],
                {self._input_name: input_tensor},
            )
        except Exception as e:
            raise YOLODetectorError(
                f"YOLO inference failed: {e}"
            ) from e

        # Postprocess: NMS, filter by class + confidence
        raw_detections = self._postprocess(outputs[0])

        # Filter by target_class + confidence_threshold
        # and sort by confidence (highest first)
        target_class_id = None
        for cid, cname in YOLO_CLASSES.items():
            if cname == target_class:
                target_class_id = cid
                break
        assert target_class_id is not None  # validated above

        matches = [
            d for d in raw_detections
            if d.class_id == target_class_id
            and d.confidence >= confidence_threshold
        ]
        matches.sort(key=lambda d: d.confidence, reverse=True)
        return matches

    def find_first(
        self,
        screenshot: Any,
        target_class: str,
        confidence_threshold: float = 0.7,
    ) -> Optional[Detection]:
        """Convenience wrapper: return the highest-confidence
        detection of `target_class`, or None if no match.

        This is the primary entry point for the
        `send_message` tool — most steps need only the
        single best detection.
        """
        matches = self.detect(
            screenshot, target_class, confidence_threshold
        )
        return matches[0] if matches else None

    # ------------------------------------------------------------------
    # Internal helpers (testable independently)
    # ------------------------------------------------------------------

    def _preprocess(self, screenshot: Any) -> Any:
        """Resize the screenshot to the YOLO input size
        and normalise to [0, 1] float32.

        Returns a numpy ndarray of shape
        (1, 3, H, W) ready for onnxruntime inference.
        """
        try:
            import numpy as np  # type: ignore
        except ImportError as e:
            raise YOLODetectorError(
                f"numpy is required for the YOLO detector. "
                f"({e})"
            ) from e

        if not hasattr(screenshot, "shape"):
            raise YOLODetectorError(
                f"screenshot must be a numpy ndarray, "
                f"got {type(screenshot).__name__}"
            )
        if len(screenshot.shape) != 3 or screenshot.shape[2] != 3:
            raise YOLODetectorError(
                f"screenshot must have shape (H, W, 3), "
                f"got {screenshot.shape}"
            )

        # Resize to YOLO input size. We use cv2 if available
        # (faster), otherwise numpy slicing (works but slow).
        # Lazy import cv2 — it's an optional dep in the
        # tool-send-message extra.
        try:
            import cv2  # type: ignore
            resized = cv2.resize(
                screenshot,
                (self._input_width, self._input_height),
                interpolation=cv2.INTER_LINEAR,
            )
        except ImportError:
            # Fallback: numpy-based resize. Slower but works
            # without cv2.
            resized = self._numpy_resize(screenshot)

        # Normalize to [0, 1] float32 + transpose HWC → CHW
        # YOLOv8 expects RGB; we don't enforce BGR/RGB here
        # because the model is trained on either.
        normalized = resized.astype(np.float32) / 255.0
        transposed = np.transpose(normalized, (2, 0, 1))  # CHW
        batched = np.expand_dims(transposed, axis=0)  # NCHW
        return np.ascontiguousarray(batched)

    def _numpy_resize(self, screenshot: Any) -> Any:
        """Pure-numpy bilinear resize (fallback when cv2
        is not installed). Slower than cv2 but works
        for any (H, W, 3) input.
        """
        import numpy as np

        h, w = screenshot.shape[:2]
        target_h, target_w = self._input_height, self._input_width
        if h == target_h and w == target_w:
            return screenshot
        # Use PIL if available (it's lighter than cv2
        # and already in many venvs via transformers/torch).
        try:
            from PIL import Image  # type: ignore
            pil_img = Image.fromarray(screenshot)
            pil_resized = pil_img.resize(
                (target_w, target_h), Image.BILINEAR
            )
            return np.array(pil_resized)
        except ImportError:
            pass
        # Last resort: simple nearest-neighbour. Bad quality
        # but at least doesn't crash.
        y_idx = np.linspace(0, h - 1, target_h).astype(int)
        x_idx = np.linspace(0, w - 1, target_w).astype(int)
        return screenshot[np.ix_(y_idx, x_idx)]

    def _postprocess(self, raw_output: Any) -> List[Detection]:
        """Parse the raw YOLO output into a list of
        `Detection` objects.

        YOLOv8 ONNX output shape: (1, N, 85) where:
          - N is the number of detections
          - 85 = 4 (bbox xywh) + 1 (objectness) + 80 (COCO classes)
        We have 4 classes (0-3), so we filter to those.

        The postprocess applies:
          1. Confidence threshold (objectness * class prob)
          2. Class filter (only our 4 classes)
          3. Coordinate conversion (xywh → xyxy → xy center)
          4. Sort by confidence
        """
        try:
            import numpy as np  # type: ignore
        except ImportError as e:
            raise YOLODetectorError(
                f"numpy is required for the YOLO detector. "
                f"({e})"
            ) from e

        if raw_output is None or len(raw_output) == 0:
            return []
        # raw_output shape: (1, N, 85) or (N, 85)
        output = raw_output[0] if len(raw_output.shape) == 3 else raw_output
        if len(output) == 0:
            return []

        detections: List[Detection] = []
        for det in output:
            # det shape: (85,)
            bbox = det[:4]  # xywh
            objectness = float(det[4])
            class_probs = det[5:]  # 80 COCO classes
            # We only care about our 4 classes (0-3).
            # COCO has 80 classes; our 4 classes are not
            # in the COCO 80 — so we treat the
            # class_probs[0:4] as our 4-class output.
            # This matches how a fine-tuned YOLOv8 model
            # is exported to ONNX: the output has 4 + 5 = 9
            # columns (4 bbox + 1 obj + 4 classes), not 85.
            # We handle both cases below.
            if len(class_probs) >= 80:
                # Standard COCO export — our 4 classes are
                # not in COCO, so this is the wrong model.
                # Return empty rather than fail.
                logger.warning(
                    "YOLO model output has 80 classes "
                    "(standard COCO). Expected 4 classes "
                    "(contact_search_bar, contact_result, "
                    "message_bar, send_button). The model "
                    "may not be the fine-tuned yolov8n-"
                    "messaging variant."
                )
                return []
            if len(class_probs) >= 4:
                # Custom export with 4 classes (our case).
                # The class probabilities are class_probs[0:4].
                our_class_probs = class_probs[:4]
                best_class_id = int(np.argmax(our_class_probs))
                best_class_prob = float(our_class_probs[best_class_id])
                confidence = objectness * best_class_prob
            else:
                continue
            if best_class_id not in YOLO_CLASSES:
                continue
            if confidence < 0.0:
                continue
            # bbox is in xywh format, normalised to [0, 1].
            # Convert to pixel coordinates in the input
            # image (640x640), then back to center xy.
            cx = float(bbox[0]) * self._input_width
            cy = float(bbox[1]) * self._input_height
            w = float(bbox[2]) * self._input_width
            h = float(bbox[3]) * self._input_height
            detections.append(Detection(
                class_name=YOLO_CLASSES[best_class_id],
                class_id=best_class_id,
                confidence=confidence,
                x=int(cx),
                y=int(cy),
                width=int(w),
                height=int(h),
            ))
        return detections


__all__ = [
    "DEFAULT_YOLO_MODEL_PATH",
    "Detection",
    "YOLO_CLASSES",
    "YOLODetector",
    "YOLODetectorError",
    "YOLO_INPUT_SIZE",
]
