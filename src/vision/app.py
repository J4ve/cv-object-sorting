"""Local live demo for the RealWaste 5-class waste classifier.

Midterm 'SEE and RECOGNIZE' demonstration: upload one or more images, use a
live streaming webcam, or try the preloaded sample images, and see each one
classified side by side with its predicted class, confidence, top-3
probability bars, and inference latency.

Robot integration (deciding a sorting destination and moving/sorting the
object) is planned for the Final project; this page only covers SEE and
RECOGNIZE. See src/vision/classifier.py for the reusable inference module
the Final project's robot loop will import.

Runs fully offline: Gradio analytics are disabled and nothing is fetched at
runtime beyond the local model and local images.

Run with: python src/vision/app.py
"""
import base64
import io
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.vision.classifier import CONF_THRESH, WasteClassifier  # noqa: E402

HOST = "127.0.0.1"
PORT = 7860
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
STREAM_MIN_INTERVAL_S = 0.3  # throttles live-webcam predictions to a few per second

print("Loading model...")
classifier = WasteClassifier()
print(f"Model ready. Classes: {classifier.class_names}")

_last_stream_ts = 0.0


CLASS_COLORS = {
    "Cardboard": "#92400e",
    "Glass": "#0f766e",
    "Metal": "#334155",
    "Paper": "#1d4ed8",
    "Plastic": "#b91c1c",
    "Uncertain": "#d97706",
}


def _thumb_data_uri(image: Image.Image, max_side: int = 360) -> str:
    img = image.copy()
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _bars_html(probabilities: dict, top_n: int = 3) -> str:
    top = sorted(probabilities.items(), key=lambda kv: -kv[1])[:top_n]
    rows = []
    for cls, p in top:
        pct = p * 100
        rows.append(
            f"""
            <div style="margin:8px 0;">
              <div style="display:flex; justify-content:space-between; font-size:1.05em;">
                <span>{cls}</span><span>{pct:.1f}%</span>
              </div>
              <div style="background:#e5e7eb; border-radius:6px; height:16px;">
                <div style="background:#4c78a8; width:{pct:.1f}%; height:16px; border-radius:6px;"></div>
              </div>
            </div>
            """
        )
    return "".join(rows)


def _card_html(image: Image.Image, title: str, result: dict | None, error: str | None = None) -> str:
    thumb = _thumb_data_uri(image)
    if error:
        body = f'<p style="color:#b91c1c; font-size:1.1em;">Could not classify this image: {error}</p>'
    else:
        color = CLASS_COLORS.get(result["label"], "#334155")
        body = (
            f'<p style="margin:4px 0; font-weight:800; font-size:2.6em; line-height:1.1; color:{color};">'
            f'{result["label"]} '
            f'<span style="font-size:0.5em; font-weight:600; color:#374151;">{result["confidence"] * 100:.1f}%</span>'
            f'<span style="font-size:0.32em; font-weight:400; color:#6b7280;"> ({result["latency_ms"]:.0f} ms)</span></p>'
            f"{_bars_html(result['probabilities'])}"
        )
    return f"""
    <div style="display:flex; gap:16px; border:1px solid #e5e7eb; border-radius:10px; padding:14px; margin-bottom:14px; align-items:flex-start;">
      <img src="{thumb}" style="width:220px; height:220px; object-fit:cover; border-radius:8px; flex-shrink:0;"/>
      <div style="flex:1; min-width:0;">
        <p style="margin:0 0 4px 0; font-size:0.85em; color:#6b7280; word-break:break-all;">{title}</p>
        {body}
      </div>
    </div>
    """


def classify_batch(files):
    """Runs a batch of uploaded images and returns one side-by-side HTML card per image."""
    if not files:
        return "<p>Upload one or more images to classify them.</p>"
    cards = []
    for f in files:
        path = f.name if hasattr(f, "name") else f
        title = Path(str(path)).name
        try:
            img = Image.open(path)
            img.load()
        except Exception as exc:
            cards.append(_card_html(Image.new("RGB", (140, 140), "#ccc"), title, None, error=str(exc)))
            continue
        try:
            result = classifier.predict(img)
            cards.append(_card_html(img, title, result))
        except Exception:
            cards.append(
                _card_html(img, title, None, error="internal error during classification")
            )
            traceback.print_exc()
    return "".join(cards)


def classify_sample(image):
    """Classifies one of the preloaded example images (used by gr.Examples)."""
    if image is None:
        return "<p>Pick a sample image above.</p>"
    result = classifier.predict(image)
    return _card_html(image, "sample image", result)


def classify_stream(frame):
    """Throttled live-webcam callback: classifies at most a few frames per second so the
    demo stays responsive instead of saturating on every incoming frame."""
    global _last_stream_ts
    if frame is None:
        return gr.skip()
    now = time.monotonic()
    if now - _last_stream_ts < STREAM_MIN_INTERVAL_S:
        return gr.skip()
    _last_stream_ts = now
    try:
        result = classifier.predict(frame)
    except Exception:
        traceback.print_exc()
        return "<p style='color:#b91c1c;'>Could not read this camera frame.</p>"
    return _card_html(frame, "live camera", result)


SCREEN_SHARE_CSS = """
.tab-nav button { font-size: 1.3em !important; font-weight: 700 !important; }
body, .gradio-container { font-size: 1.3em; }
"""

with gr.Blocks(title="Waste Classifier (RealWaste, Midterm demo)", analytics_enabled=False) as demo:
    gr.Markdown("# Waste Classifier - SEE and RECOGNIZE")
    gr.Markdown(
        "Upload images, use the live webcam, or try a sample below to classify waste "
        f"into 5 RealWaste classes (predictions under {CONF_THRESH * 100:.0f}% confidence show as 'Uncertain')."
    )
    gr.Markdown(
        "_Planned for the Final project: using this recognition to decide a sorting "
        "destination and drive a 4WD robot to act on it._"
    )

    with gr.Tab("Upload / batch"):
        file_input = gr.File(file_count="multiple", file_types=["image"], label="Upload one or more images")
        batch_out = gr.HTML()
        file_input.change(classify_batch, inputs=file_input, outputs=batch_out)

        sample_paths = sorted(str(p) for p in SAMPLES_DIR.glob("*.jpg")) if SAMPLES_DIR.exists() else []
        if sample_paths:
            gr.Markdown(
                "**Or try a sample image** (held-out test images, RealWaste dataset, "
                "CC BY-NC-SA 4.0 per the authors' IEEE DataPort listing):"
            )
            sample_input = gr.Image(type="pil", visible=False)
            sample_out = gr.HTML()
            gr.Examples(examples=sample_paths, inputs=sample_input, outputs=sample_out, fn=classify_sample, run_on_click=True)

    with gr.Tab("Live camera"):
        gr.Markdown(
            "Allow camera access, then click the camera icon to start streaming. "
            "If no webcam is available, use the Upload tab instead."
        )
        cam_input = gr.Image(sources=["webcam"], streaming=True, type="pil", label="Live webcam")
        cam_out = gr.HTML()
        cam_input.stream(classify_stream, inputs=cam_input, outputs=cam_out, stream_every=0.2)


if __name__ == "__main__":
    demo.launch(
        server_name=HOST,
        server_port=PORT,
        show_error=True,
        share=False,
        inbrowser=False,
        theme=gr.themes.Default(text_size="lg"),
        css=SCREEN_SHARE_CSS,
    )
