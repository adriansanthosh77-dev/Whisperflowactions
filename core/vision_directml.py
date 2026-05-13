import os
import logging
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_DIR = Path("data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

CLASSIFICATION_MODEL_PATH = MODEL_DIR / "squeezenet1.0-7.onnx"
CLASSIFICATION_MODEL_URL = "https://github.com/onnx/models/raw/main/validated/vision/classification/squeezenet/model/squeezenet1.0-7.onnx"

IMAGENET_LABELS_URL = "https://raw.githubusercontent.com/anishathalye/imagenet-simple-labels/master/imagenet-simple-labels.json"
IMAGENET_LABELS_PATH = MODEL_DIR / "imagenet_labels.json"


def _get_providers():
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        providers = []
        if "DmlExecutionProvider" in available:
            providers.append("DmlExecutionProvider")
        providers.append("CPUExecutionProvider")
        return providers, available
    except ImportError:
        return None, []


def is_directml_available() -> bool:
    providers, _ = _get_providers()
    return providers is not None and "DmlExecutionProvider" in providers


def _download_file(url: str, dest: Path, desc: str = "file"):
    if dest.exists():
        return True
    logger.info(f"Downloading {desc} from {url}...")
    try:
        urllib.request.urlretrieve(url, str(dest))
        logger.info(f"Downloaded {desc} to {dest}")
        return True
    except Exception as e:
        logger.warning(f"Failed to download {desc}: {e}")
        return False


def _ensure_imagenet_labels() -> list:
    if IMAGENET_LABELS_PATH.exists():
        try:
            import json
            with open(IMAGENET_LABELS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    if _download_file(IMAGENET_LABELS_URL, IMAGENET_LABELS_PATH, "ImageNet labels"):
        try:
            import json
            with open(IMAGENET_LABELS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return []


class DirectMLVision:
    def __init__(self):
        self._session = None
        self._labels = []
        self._providers = []
        self._initialized = False

    def _init(self):
        if self._initialized:
            return
        self._initialized = True
        providers, _ = _get_providers()
        self._providers = providers or []
        if not self._providers:
            return
        if CLASSIFICATION_MODEL_PATH.exists() or _download_file(
            CLASSIFICATION_MODEL_URL, CLASSIFICATION_MODEL_PATH, "SqueezeNet ONNX"
        ):
            self._labels = _ensure_imagenet_labels()
            try:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self._session = ort.InferenceSession(
                    str(CLASSIFICATION_MODEL_PATH), opts, providers=self._providers
                )
                logger.info(f"DirectML session ready. Providers: {self._providers}")
            except Exception as e:
                logger.warning(f"DirectML session creation failed: {e}")

    def is_available(self) -> bool:
        if not self._initialized:
            self._init()
        return bool(self._providers)

    def classify_image(self, screenshot_path: str, top_k: int = 5) -> list[dict]:
        self._init()
        if not self._session:
            return []
        try:
            from PIL import Image
            import numpy as np
            img = Image.open(screenshot_path).convert("RGB").resize((224, 224))
            arr = np.array(img, dtype=np.float32).transpose(2, 0, 1)[np.newaxis, :, :, :] / 255.0
            mean = np.array([0.485, 0.456, 0.406]).reshape(1, 3, 1, 1)
            std = np.array([0.229, 0.224, 0.225]).reshape(1, 3, 1, 1)
            arr = (arr - mean) / std

            input_name = self._session.get_inputs()[0].name
            outputs = self._session.run(None, {input_name: arr.astype(np.float32)})
            probs = outputs[0][0]

            import numpy as np2
            top_indices = np2.argsort(probs)[::-1][:top_k]
            results = []
            for idx in top_indices:
                label = self._labels[int(idx)] if int(idx) < len(self._labels) else f"class_{int(idx)}"
                results.append({
                    "label": label,
                    "confidence": round(float(probs[idx]), 4),
                })
            return results
        except Exception as e:
            logger.warning(f"DirectML classification failed: {e}")
            return []

    def analyze_screenshot(self, screenshot_path: str, prompt: str) -> Optional[str]:
        results = self.classify_image(screenshot_path, top_k=3)
        if not results:
            return None
        top = results[0]
        return f"[DirectML] Top prediction: {top['label']} ({top['confidence']:.1%})"

    def detect_objects(self, screenshot_path: str) -> list[dict]:
        return self.classify_image(screenshot_path, top_k=5)

    def find_object(self, screenshot_path: str, target: str) -> Optional[dict]:
        results = self.detect_objects(screenshot_path)
        target_lower = target.lower()
        for r in results:
            if target_lower in r["label"].lower():
                return r
        return None


_dml_instance = None
def get_directml_vision():
    global _dml_instance
    if _dml_instance is None:
        _dml_instance = DirectMLVision()
    return _dml_instance
