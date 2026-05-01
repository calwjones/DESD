import base64
import io

import cv2
import numpy as np
import tensorflow as tf
from PIL import Image
from tensorflow import keras

IMG_SIZE = (224, 224)


class Explainer:
    def __init__(self, model_manager, grader):
        self.model_manager = model_manager
        self.grader = grader

    def generate_gradcam(self, image_bytes, last_conv_layer_name="out_relu"):
        snapshot = self.model_manager.snapshot()
        if snapshot is None:
            raise ValueError("No model loaded")
        model, _, ext = snapshot
        if ext not in (".keras", ".h5"):
            raise ValueError("Grad-CAM requires a Keras image model (.keras or .h5)")

        grading_result = self.grader.grade(image_bytes)

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_resized = img.resize(IMG_SIZE)
        img_array = np.array(img_resized, dtype=np.float32) / 255.0
        batch = np.expand_dims(img_array, axis=0)

        base_model = model.get_layer("mobilenetv2_1.00_224")
        base_cam_model = keras.models.Model(
            inputs=base_model.input,
            outputs=[
                base_model.get_layer(last_conv_layer_name).output,
                base_model.output,
            ],
        )

        inputs = model.input
        conv_tensor, x = base_cam_model(inputs)
        x = model.get_layer("global_average_pooling2d")(x)
        x = model.get_layer("dropout")(x)
        x = model.get_layer("feature_layer")(x)
        x = model.get_layer("dropout_1")(x)
        predictions_tensor = model.get_layer("classification")(x)

        grad_model = keras.models.Model(inputs=inputs, outputs=[conv_tensor, predictions_tensor])

        with tf.GradientTape() as tape:
            conv_outputs, predictions = grad_model(batch, training=False)
            if predictions.shape[-1] == 1:
                class_channel = predictions[:, 0]
            else:
                pred_index = tf.argmax(predictions[0])
                class_channel = predictions[:, pred_index]

        grads = tape.gradient(class_channel, conv_outputs)
        if grads is None:
            raise ValueError(f"Gradients are None for layer '{last_conv_layer_name}'")

        if len(grads.shape) == 4:
            pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))
        elif len(grads.shape) == 2:
            pooled_grads = tf.reduce_mean(grads, axis=0)
        else:
            raise ValueError(f"Unexpected gradient shape: {grads.shape}")

        conv_outputs = conv_outputs[0].numpy()
        pooled_grads = pooled_grads.numpy()

        if len(conv_outputs.shape) == 3:
            for i in range(len(pooled_grads)):
                conv_outputs[:, :, i] *= pooled_grads[i]
            heatmap = np.mean(conv_outputs, axis=-1)
        elif len(conv_outputs.shape) == 1:
            heatmap = np.full((7, 7), float(np.mean(conv_outputs * pooled_grads)))
        else:
            raise ValueError(f"Unexpected conv_output shape: {conv_outputs.shape}")

        heatmap = np.maximum(heatmap, 0)
        max_val = np.max(heatmap)
        heatmap = heatmap / max_val if max_val != 0 else heatmap

        heatmap_resized = cv2.resize(heatmap, (img.width, img.height))
        heatmap_coloured = cv2.applyColorMap(np.uint8(255 * heatmap_resized), cv2.COLORMAP_JET)
        superimposed = cv2.addWeighted(np.array(img), 0.6, heatmap_coloured, 0.4, 0)

        _, buffer = cv2.imencode(".png", superimposed)
        heatmap_base64 = base64.b64encode(buffer).decode("utf-8")

        return {
            "heatmap_base64": heatmap_base64,
            "explanation": self._describe_focus(
                heatmap_resized, grading_result["confidence"], grading_result["prediction"]
            ),
            "confidence": grading_result["confidence"],
            "predicted_class": grading_result["prediction"],
            "grade": grading_result["grade"],
            "color_score": grading_result["color_score"],
            "size_score": grading_result["size_score"],
            "ripeness_score": grading_result["ripeness_score"],
            "model_version": grading_result["model_version"],
            "recommended_action": "Recommend discount" if grading_result["grade"] == "C" else None,
        }

    def _describe_focus(self, heatmap, confidence, predicted_class):
        high_activation = np.where(heatmap > 0.7 * np.max(heatmap))
        if len(high_activation[0]) == 0:
            return (
                f"Predicted as '{predicted_class}' with {confidence:.1%} confidence "
                "based on overall image features."
            )

        height, width = heatmap.shape[:2]
        avg_y = np.mean(high_activation[0])
        avg_x = np.mean(high_activation[1])

        if avg_y < height * 0.33:
            region = "top"
        elif avg_y > height * 0.66:
            region = "bottom"
        else:
            region = "middle"

        if avg_x < width * 0.33:
            region += "-left"
        elif avg_x > width * 0.66:
            region += "-right"
        else:
            region += "-center"

        return (
            f"Predicted as '{predicted_class}' with {confidence:.1%} confidence. "
            f"Model focused on {region} region."
        )
