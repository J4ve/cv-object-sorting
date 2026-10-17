"""Reusable waste-classification inference, separate from any UI.

Loads the MobileNetV2-based model exported by src/training/train_export.py and
classifies images with the exact preprocessing the model expects: resize to
IMG_SIZE and feed raw 0-255 RGB (the model itself contains the Rescaling(1/127.5,
offset=-1) layer, so no external normalization is applied here).

Intended to be imported both by the local demo (src/vision/app.py) and, later,
by the Final project's robot SEE-DECIDE-ACT loop.
"""
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = REPO_ROOT / "models" / "waste_classifier.keras"
DEFAULT_CLASS_NAMES_PATH = REPO_ROOT / "models" / "class_names.json"
DEFAULT_CLASS_THRESHOLDS_PATH = REPO_ROOT / "models" / "class_thresholds.json"
IMG_SIZE = (224, 224)
# Global fallback threshold: selected on the validation set (smallest t with validation
# selective accuracy >= 90%), not hand-picked. See results/threshold_selection.json for
# the full sweep. Per-predicted-class thresholds (models/class_thresholds.json, selected
# the same way per class on validation; see results/class_thresholds.json) take priority
# when available, since classes are not equally precise at the same confidence level;
# this value is only the fallback for a class missing from that file.
CONF_THRESH = 0.59


class WasteClassifier:
    """Loads the trained model once and classifies images from it."""

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        class_names_path: Path = DEFAULT_CLASS_NAMES_PATH,
        class_thresholds_path: Path = DEFAULT_CLASS_THRESHOLDS_PATH,
    ):
        import tensorflow as tf  # imported lazily so callers that only need types stay light

        model_path = Path(model_path)
        class_names_path = Path(class_names_path)
        class_thresholds_path = Path(class_thresholds_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. Run src/training/train_export.py first."
            )
        self.model = tf.keras.models.load_model(model_path)
        self.class_names = json.load(open(class_names_path))
        per_class = json.load(open(class_thresholds_path)) if class_thresholds_path.exists() else {}
        # Every class falls back to CONF_THRESH if missing from the file.
        self.class_thresholds = {c: per_class.get(c, CONF_THRESH) for c in self.class_names}
        self._infer = tf.function(lambda x: self.model(x, training=False))
        self._warm_up()

    def _warm_up(self):
        """Runs one dummy inference so the first real prediction isn't slowed by lazy init
        or by tf.function's one-time tracing/compilation cost."""
        dummy = np.zeros((1, *IMG_SIZE, 3), dtype=np.float32)
        self._infer(dummy)

    def preprocess(self, image: Image.Image) -> np.ndarray:
        """Converts any PIL image to the raw 0-255 RGB array the model expects."""
        image = ImageOps.exif_transpose(image)  # phone photos otherwise arrive rotated
        rgb = image.convert("RGB")
        resized = rgb.resize(IMG_SIZE, Image.Resampling.BILINEAR)
        return np.asarray(resized, dtype=np.float32)

    def predict(self, image: Image.Image) -> dict:
        """Classifies one PIL image. Returns label, confidence, per-class probabilities,
        latency in ms, and whether confidence cleared that predicted class's own
        threshold ('Uncertain' otherwise; see class_thresholds in __init__)."""
        t0 = time.perf_counter()
        x = self.preprocess(image)
        probs = self._infer(x[None, ...]).numpy()[0]
        latency_ms = (time.perf_counter() - t0) * 1000
        idx = int(probs.argmax())
        conf = float(probs[idx])
        raw_label = self.class_names[idx]
        threshold = self.class_thresholds[raw_label]
        is_uncertain = conf < threshold
        label = raw_label if not is_uncertain else "Uncertain"
        return {
            "label": label,
            "raw_label": raw_label,
            "confidence": conf,
            "probabilities": {c: float(p) for c, p in zip(self.class_names, probs)},
            "is_uncertain": is_uncertain,
            "threshold_used": threshold,
            "latency_ms": latency_ms,
        }
