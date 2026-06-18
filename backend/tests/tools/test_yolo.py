"""Tests for the YOLO detector (Sprint 30 Track A).

Per `docs/FEATURE-SPEC-SPRINT30.md` §4.1.

The YOLO detector wraps a YOLOv8n ONNX model +
onnxruntime inference. The real model can't run in CI
(no display, no model file). The tests mock the
onnxruntime InferenceSession and verify the contract:

  1. Model file missing → clear error
  2. onnxruntime missing → clear error
  3. Preprocess (resize + normalize) shape
  4. Postprocess (NMS, class filter, confidence)
  5. detect() returns matches sorted by confidence
  6. find_first() returns the highest-confidence match
  7. Target class validation
  8. Invalid screenshot shape
  9. Empty raw output
  10. Standard COCO model (80 classes) returns empty
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.tools._yolo import (
    DEFAULT_YOLO_MODEL_PATH,
    YOLO_CLASSES,
    YOLODetector,
    YOLODetectorError,
    YOLO_INPUT_SIZE,
    Detection,
)


# ---------------------------------------------------------------------------
# 1. Constants + class structure
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_model_path(self):
        # Default path is ~/.gundam-halo/models/yolov8n-messaging.onnx
        assert DEFAULT_YOLO_MODEL_PATH.name == "yolov8n-messaging.onnx"
        assert ".gundam-halo" in str(DEFAULT_YOLO_MODEL_PATH)

    def test_yolo_classes_count(self):
        # 4 classes per spec §4.1
        assert len(YOLO_CLASSES) == 4

    def test_yolo_class_ids(self):
        # Class IDs 0-3, per spec §4.1
        assert YOLO_CLASSES[0] == "contact_search_bar"
        assert YOLO_CLASSES[1] == "contact_result"
        assert YOLO_CLASSES[2] == "message_bar"
        assert YOLO_CLASSES[3] == "send_button"

    def test_yolo_input_size(self):
        # YOLOv8n default is 640x640
        assert YOLO_INPUT_SIZE == 640


# ---------------------------------------------------------------------------
# 2. Model file missing
# ---------------------------------------------------------------------------


class TestModelFileMissing:
    def test_raises_clear_error_when_model_missing(self, tmp_path):
        missing_model = tmp_path / "missing.onnx"
        with pytest.raises(YOLODetectorError) as excinfo:
            YOLODetector(model_path=missing_model)
        # Error message should mention download script
        assert "download_yolo_model.py" in str(excinfo.value)
        assert str(missing_model) in str(excinfo.value)

    def test_accepts_string_path(self, tmp_path):
        # __init__ should accept a string OR a Path
        missing_model = tmp_path / "missing.onnx"
        with pytest.raises(YOLODetectorError):
            YOLODetector(model_path=str(missing_model))


# ---------------------------------------------------------------------------
# 3. onnxruntime missing
# ---------------------------------------------------------------------------


class TestOnnxruntimeMissing:
    def test_raises_clear_error_when_onnxruntime_missing(self, tmp_path):
        # Create a fake model file (just needs to exist)
        fake_model = tmp_path / "fake.onnx"
        fake_model.write_bytes(b"onnx" + b"\x00" * 100)

        with patch.dict("sys.modules", {"onnxruntime": None}):
            import importlib
            importlib.invalidate_caches()
            with pytest.raises(YOLODetectorError) as excinfo:
                YOLODetector(model_path=fake_model)
            assert "onnxruntime" in str(excinfo.value)
            assert "tool-send-message" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 4. Successful init + inference (mocked)
# ---------------------------------------------------------------------------


def _make_fake_onnxruntime_session(num_classes: int = 4):
    """Create a mock onnxruntime.InferenceSession that
    returns a controlled output.
    """
    session = MagicMock()
    # Input/output names + shapes
    session.get_inputs.return_value = [
        MagicMock(name="images", shape=[1, 3, YOLO_INPUT_SIZE, YOLO_INPUT_SIZE])
    ]
    session.get_outputs.return_value = [
        MagicMock(name="output0", shape=[1, 1, num_classes + 5])
    ]
    return session


class TestInference:
    def _make_detector_with_mock_session(self, num_classes: int = 4, tmp_path=None):
        """Helper: create a YOLODetector with a mocked
        onnxruntime session.
        """
        if tmp_path is None:
            tmp_path = Path("/tmp")
        fake_model = tmp_path / "fake.onnx"
        fake_model.write_bytes(b"onnx" + b"\x00" * 100)
        with patch("onnxruntime.InferenceSession") as mock_session_class:
            mock_session_class.return_value = _make_fake_onnxruntime_session(num_classes)
            detector = YOLODetector(model_path=fake_model)
        return detector

    def test_init_succeeds_with_mock(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)
        assert detector.model_path.exists()
        assert detector.input_size == (YOLO_INPUT_SIZE, YOLO_INPUT_SIZE)

    def test_detect_returns_matches_sorted_by_confidence(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        # Mock the session.run() to return a controlled output.
        # YOLOv8 output: (1, N, 9) where N=number of detections,
        # 9 = 4 bbox xywh + 1 obj + 4 class probs.
        import numpy as np
        raw_output = np.array([[
            # 3 detections, all of class 0 (contact_search_bar),
            # different confidences
            [0.5, 0.5, 0.1, 0.1, 0.9, 0.8, 0.1, 0.05, 0.05],  # conf = 0.9 * 0.8 = 0.72
            [0.3, 0.3, 0.1, 0.1, 0.95, 0.9, 0.05, 0.03, 0.02],  # conf = 0.95 * 0.9 = 0.855
            [0.7, 0.7, 0.1, 0.1, 0.8, 0.7, 0.2, 0.05, 0.05],  # conf = 0.8 * 0.7 = 0.56
        ]], dtype=np.float32)
        detector._session.run = MagicMock(return_value=[raw_output])

        # Mock the screenshot as a numpy array of shape (480, 640, 3)
        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        matches = detector.detect(
            screenshot, "contact_search_bar", confidence_threshold=0.5
        )

        # All 3 detections should be returned (above 0.5 threshold)
        assert len(matches) == 3
        # Sorted by confidence (highest first)
        assert matches[0].confidence > matches[1].confidence > matches[2].confidence
        # First match is the one with conf 0.855
        assert abs(matches[0].confidence - 0.855) < 0.001

    def test_detect_filters_by_class(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        import numpy as np
        raw_output = np.array([[
            # 2 detections: one of class 0 (search_bar),
            # one of class 2 (message_bar)
            [0.5, 0.5, 0.1, 0.1, 0.9, 0.9, 0.05, 0.03, 0.02],  # class 0
            [0.7, 0.7, 0.1, 0.1, 0.9, 0.05, 0.05, 0.85, 0.05],  # class 2
        ]], dtype=np.float32)
        detector._session.run = MagicMock(return_value=[raw_output])

        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        # Filter to "contact_search_bar" — only 1 match
        matches = detector.detect(
            screenshot, "contact_search_bar", confidence_threshold=0.5
        )
        assert len(matches) == 1
        assert matches[0].class_name == "contact_search_bar"

    def test_detect_filters_by_confidence_threshold(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        import numpy as np
        raw_output = np.array([[
            # 2 detections, both class 0, different confidences
            [0.5, 0.5, 0.1, 0.1, 0.9, 0.9, 0.05, 0.03, 0.02],  # conf = 0.81
            [0.3, 0.3, 0.1, 0.1, 0.5, 0.5, 0.3, 0.1, 0.1],  # conf = 0.25
        ]], dtype=np.float32)
        detector._session.run = MagicMock(return_value=[raw_output])

        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        # Threshold 0.5: only the high-confidence one
        matches = detector.detect(
            screenshot, "contact_search_bar", confidence_threshold=0.5
        )
        assert len(matches) == 1
        assert matches[0].confidence > 0.5

    def test_find_first_returns_highest_confidence(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        import numpy as np
        raw_output = np.array([[
            [0.5, 0.5, 0.1, 0.1, 0.9, 0.9, 0.05, 0.03, 0.02],  # conf 0.81
            [0.3, 0.3, 0.1, 0.1, 0.95, 0.95, 0.03, 0.01, 0.01],  # conf 0.9025
        ]], dtype=np.float32)
        detector._session.run = MagicMock(return_value=[raw_output])

        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        best = detector.find_first(
            screenshot, "contact_search_bar", confidence_threshold=0.5
        )
        assert best is not None
        assert abs(best.confidence - 0.9025) < 0.001

    def test_find_first_returns_none_when_no_match(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        import numpy as np
        raw_output = np.array([[
            [0.5, 0.5, 0.1, 0.1, 0.9, 0.9, 0.05, 0.03, 0.02],  # conf 0.81
        ]], dtype=np.float32)
        detector._session.run = MagicMock(return_value=[raw_output])

        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        # Looking for "message_bar" but no such class in output
        best = detector.find_first(
            screenshot, "message_bar", confidence_threshold=0.5
        )
        assert best is None

    def test_detect_raises_on_unknown_target_class(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        import numpy as np
        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        with pytest.raises(YOLODetectorError) as excinfo:
            detector.detect(screenshot, "not_a_real_class", 0.5)
        assert "Unknown target_class" in str(excinfo.value)

    def test_detect_returns_empty_for_coco_model(self, tmp_path):
        # Standard COCO model has 80 classes — should return empty
        detector = self._make_detector_with_mock_session(num_classes=80, tmp_path=tmp_path)

        import numpy as np
        # COCO-style output: 85 columns (4 bbox + 1 obj + 80 classes)
        raw_output = np.zeros((1, 1, 85), dtype=np.float32)
        detector._session.run = MagicMock(return_value=[raw_output])

        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        matches = detector.detect(
            screenshot, "contact_search_bar", confidence_threshold=0.5
        )
        # COCO model doesn't have our 4 classes — return empty
        assert matches == []

    def test_detect_handles_empty_raw_output(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)
        # Empty output
        import numpy as np
        detector._session.run = MagicMock(return_value=[np.zeros((1, 0, 9), dtype=np.float32)])

        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        matches = detector.detect(
            screenshot, "contact_search_bar", confidence_threshold=0.5
        )
        assert matches == []

    def test_preprocess_validates_screenshot_shape(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        # Not a numpy array
        with pytest.raises(YOLODetectorError) as excinfo:
            detector._preprocess("not_an_array")
        assert "numpy ndarray" in str(excinfo.value)

        # Wrong shape (not HxWx3)
        import numpy as np
        with pytest.raises(YOLODetectorError) as excinfo:
            detector._preprocess(np.zeros((100, 100), dtype=np.uint8))
        assert "shape" in str(excinfo.value)

    def test_preprocess_returns_correct_shape(self, tmp_path):
        detector = self._make_detector_with_mock_session(tmp_path=tmp_path)

        import numpy as np
        screenshot = np.zeros((480, 640, 3), dtype=np.uint8)
        tensor = detector._preprocess(screenshot)
        # Should be (1, 3, 640, 640) — batch=1, channels=3, H=640, W=640
        assert tensor.shape == (1, 3, YOLO_INPUT_SIZE, YOLO_INPUT_SIZE)
        # Should be float32 in [0, 1]
        assert tensor.dtype == np.float32
        assert tensor.min() >= 0.0
        assert tensor.max() <= 1.0


# ---------------------------------------------------------------------------
# 5. Detection dataclass
# ---------------------------------------------------------------------------


class TestDetection:
    def test_to_dict(self):
        det = Detection(
            class_name="contact_search_bar",
            class_id=0,
            confidence=0.95,
            x=100,
            y=200,
            width=80,
            height=20,
        )
        d = det.to_dict()
        assert d["class_name"] == "contact_search_bar"
        assert d["class_id"] == 0
        assert d["confidence"] == 0.95
        assert d["x"] == 100
        assert d["y"] == 200
        assert d["width"] == 80
        assert d["height"] == 20
