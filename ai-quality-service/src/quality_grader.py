import io
import numpy as np
import cv2
from model_upload import ModelManager

IMG_SIZE = (224, 224)


def _preprocess_image(image_bytes: bytes) -> np.ndarray:
    """load image bytes into a normalised numpy array for the model"""
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize(IMG_SIZE)
    arr = np.array(img, dtype=np.float32) / 255.0
    return arr  # shape (224, 224, 3), values 0-1


def _scores_to_grade(color: float, size: float, ripeness: float) -> str:
    """case study thresholds"""
    if color >= 75 and size >= 80 and ripeness >= 70:
        return "A"
    elif color >= 65 and size >= 70 and ripeness >= 60:
        return "B"
    else:
        return "C"


def _compute_color_score(img_array: np.ndarray, fresh_confidence: float = None) -> float:
    """
    colour vibrancy using HSV saturation.
    fresh produce has more saturated colours, rotten goes dull/brown.
    blends with model confidence so naturally pale produce like bananas
    dont get penalised just for being yellow.
    """
    img_uint8 = (img_array * 255).astype(np.uint8)
    hsv = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2HSV)

    saturation = hsv[:, :, 1].mean() / 255.0
    value = hsv[:, :, 2].mean() / 255.0
    brightness_penalty = 1.0 - abs(value - 0.55) * 0.5

    raw_score = (saturation * 0.7 + brightness_penalty * 0.3)
    score = raw_score * 120

    if fresh_confidence is not None:
        score = score * 0.5 + fresh_confidence * 100 * 0.5

    return round(float(np.clip(score, 0, 100)), 1)


def _compute_size_score(img_array: np.ndarray) -> float:
    """
    how much of the frame the produce fills.
    uses otsu thresholding to separate foreground from background.
    """
    img_uint8 = (img_array * 255).astype(np.uint8)
    gray = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2GRAY)

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    fg_ratio = np.count_nonzero(binary) / binary.size

    if fg_ratio < 0.2:
        score = fg_ratio / 0.2 * 60
    elif fg_ratio > 0.85:
        score = 85 - (fg_ratio - 0.85) * 100
    else:
        score = 70 + (fg_ratio - 0.2) / 0.5 * 30

    return round(float(np.clip(score, 0, 100)), 1)


def _compute_ripeness_score(img_array: np.ndarray, fresh_confidence: float) -> float:
    """
    combines model confidence with colour warmth.
    warm colours (reds, yellows) suggest proper ripeness,
    dark colours suggest over-ripeness.
    """
    r_mean = img_array[:, :, 0].mean()
    g_mean = img_array[:, :, 1].mean()
    b_mean = img_array[:, :, 2].mean()

    warmth = (r_mean + g_mean * 0.5) / (b_mean + 0.01)
    warmth_normalised = np.clip(warmth / 4.0, 0, 1)

    raw_score = fresh_confidence * 0.6 + warmth_normalised * 0.4
    score = np.clip(raw_score * 100, 0, 100)
    return round(float(score), 1)


class QualityGrader:
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager

    def grade(self, image_bytes: bytes) -> dict:
        snapshot = self.model_manager.snapshot()
        if snapshot is None:
            return self._dummy_result()

        model, version, ext = snapshot

        try:
            img_array = _preprocess_image(image_bytes)
            batch = np.expand_dims(img_array, axis=0)

            # get fresh/rotten prediction from model
            if ext in (".keras", ".h5"):
                predictions = model.predict(batch, verbose=0)
                # our model outputs single sigmoid: P(rotten)
                rotten_prob = float(predictions[0][0])
                fresh_confidence = 1.0 - rotten_prob

            elif ext == ".pkl":
                flat = batch.flatten().reshape(1, -1)
                fresh_confidence = float(model.predict_proba(flat)[0][1])

            else:
                return self._dummy_result()

            # compute scores from actual image properties
            color = _compute_color_score(img_array, fresh_confidence)
            size = _compute_size_score(img_array)
            ripeness = _compute_ripeness_score(img_array, fresh_confidence)

        except Exception as e:
            print(f"Grading error: {e}")
            return self._dummy_result()

        grade = _scores_to_grade(color, size, ripeness)

        return {
            "prediction": "Fresh" if fresh_confidence > 0.5 else "Rotten",
            "confidence": round(max(fresh_confidence, 1.0 - fresh_confidence), 4),
            "grade": grade,
            "color_score": color,
            "size_score": size,
            "ripeness_score": ripeness,
            "model_version": version,
            "recommended_action": "Recommend discount" if grade == "C" else None
        }

    def _dummy_result(self) -> dict:
        return {
            "prediction": "Unknown",
            "confidence": 0.0,
            "grade": "C",
            "color_score": 0.0,
            "size_score": 0.0,
            "ripeness_score": 0.0,
            "model_version": "no-model-loaded",
            "note": "No model loaded. Upload a model first via /upload-model.",
        }
