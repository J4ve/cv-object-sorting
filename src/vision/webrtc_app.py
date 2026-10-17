"""Experimental real-time WebRTC phone-camera demo (FastRTC), separate from app.py.

Phones stream live video over WebRTC; this desktop samples and classifies
frames (src/vision/classifier.py) and draws the label back onto the video.
A Presenter tab polls the latest annotated frame for screen-sharing in a
video call. All classification runs on this desktop; phones only capture
and send video, matching the main demo's processing-location rule.

NAT note: public STUN only (set by captain decision, 2026-10-17). Some
phone/network combinations behind strict NAT or CGNAT will fail to connect;
the UI then points to the main demo as a fallback. An HF_TOKEN env var is
read for FastRTC's free Cloudflare TURN relay (not required; wires up
automatically if a token is ever provided later).

Run with: python src/vision/webrtc_app.py
"""
import os
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.vision.classifier import WasteClassifier  # noqa: E402

from fastrtc import WebRTC, get_cloudflare_turn_credentials  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("WEBRTC_DEMO_PORT", 7863))
SAMPLE_INTERVAL_S = 0.1  # classify at most ~10 frames/s per phone
STALE_AFTER_S = 2.0  # presenter shows "signal lost" once a device stops sending
WATCHDOG_TIMEOUT_S = 15.0  # how long to wait before suggesting the fallback link
MAIN_DEMO_URL_PLACEHOLDER = "the main demo link the captain shared"

print("Loading model...")
classifier = WasteClassifier()
print(f"Model ready. Classes: {classifier.class_names}")

CLASS_COLORS = {
    "Cardboard": "#92400e",
    "Glass": "#0f766e",
    "Metal": "#334155",
    "Paper": "#1d4ed8",
    "Plastic": "#b91c1c",
    "Uncertain": "#d97706",
}

_lock = threading.Lock()
_devices: dict[str, dict] = {}  # name -> {frame, label, conf, ts, frame_times}
_last_classify: dict[str, float] = {}


def _rtc_configuration():
    """STUN by default; switches to FastRTC's free Cloudflare TURN relay if an
    HF_TOKEN is ever set, with no code change needed."""
    hf_token = os.environ.get("HF_TOKEN")
    if hf_token:
        try:
            return get_cloudflare_turn_credentials(hf_token=hf_token)
        except Exception:
            traceback.print_exc()
    return {"iceServers": [{"urls": "stun:stun.l.google.com:19302"}]}


def _draw_label(frame: np.ndarray, label: str, conf: float, color: str) -> np.ndarray:
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, img.width, 44], fill=color)
    draw.text((12, 10), f"{label}  {conf * 100:.0f}%", fill="white")
    return np.array(img)


def video_handler(frame: np.ndarray, name: str) -> np.ndarray:
    """FastRTC per-frame callback for a phone's WebRTC stream: classifies at
    most every SAMPLE_INTERVAL_S, draws the (possibly cached) label on every
    frame so the video stays smooth, and records the frame for the Presenter
    tab to poll."""
    name = (name or "phone").strip() or "phone"
    now = time.time()
    with _lock:
        prev = _devices.get(name, {})
    label, conf = prev.get("label", "Uncertain"), prev.get("conf", 0.0)

    if now - _last_classify.get(name, 0.0) >= SAMPLE_INTERVAL_S:
        _last_classify[name] = now
        try:
            result = classifier.predict(Image.fromarray(frame))
            label, conf = result["label"], result["confidence"]
        except Exception:
            traceback.print_exc()

    annotated = _draw_label(frame, label, conf, CLASS_COLORS.get(label, "#334155"))

    with _lock:
        frame_times = _devices.get(name, {}).get("frame_times", deque(maxlen=30))
        frame_times.append(now)
        fps = (len(frame_times) - 1) / max(frame_times[-1] - frame_times[0], 1e-6) if len(frame_times) > 1 else 0.0
        _devices[name] = {
            "frame": annotated,
            "label": label,
            "conf": conf,
            "ts": now,
            "frame_times": frame_times,
            "fps": fps,
        }
    return annotated


def list_devices() -> list[str]:
    with _lock:
        return sorted(_devices.keys())


def presenter_frame(name: str | None):
    if not name:
        return None, "Pick a device above."
    with _lock:
        d = _devices.get(name)
    if not d:
        return None, "No signal yet."
    if time.time() - d["ts"] > STALE_AFTER_S:
        return d["frame"], "Signal lost (phone stopped sending)."
    return d["frame"], f"{d['label']}  {d['conf'] * 100:.0f}%  |  {d['fps']:.1f} fps"


def refresh_device_dropdown(current: str | None):
    choices = list_devices()
    value = current if current in choices else (choices[0] if choices else None)
    return gr.update(choices=choices, value=value)


def connection_watchdog(name: str, started_at: float):
    name = (name or "phone").strip() or "phone"
    now = time.time()
    if not started_at:
        return gr.update(visible=False), now
    with _lock:
        d = _devices.get(name)
    if d and now - d["ts"] < STALE_AFTER_S:
        return gr.update(visible=False), started_at
    if now - started_at > WATCHDOG_TIMEOUT_S:
        msg = (
            "**Still connecting.** If the picture hasn't appeared, your network is "
            f"likely blocking this experimental connection. Please use {MAIN_DEMO_URL_PLACEHOLDER} instead."
        )
        return gr.update(value=msg, visible=True), started_at
    return gr.update(visible=False), started_at


SCREEN_SHARE_CSS = """
.tab-nav button { font-size: 1.4em !important; font-weight: 700 !important; }
body, .gradio-container { font-size: 1.3em; }
"""

with gr.Blocks(
    title="Waste Classifier - WebRTC phone demo (experimental)", analytics_enabled=False, css=SCREEN_SHARE_CSS
) as demo:
    gr.Markdown("# Waste Classifier - WebRTC phone demo (experimental)")
    gr.Markdown(
        "_Experimental real-time version of the phone-camera demo. The main demo stays the "
        "primary link; this is only used if the captain switches to it._"
    )

    with gr.Tab("Phone camera"):
        name_box = gr.Textbox(label="Your name", placeholder="e.g. Alex's phone")
        gr.Markdown(
            "Enter your name, allow camera access, then press play. Classification runs on "
            "the captain's desktop, not on your phone."
        )
        webrtc = WebRTC(
            label="Live camera",
            mode="send-receive",
            modality="video",
            mirror_webcam=False,
            rtc_configuration=_rtc_configuration,
            track_constraints={
                "facingMode": {"ideal": "environment"},
                "width": {"ideal": 640},
                "height": {"ideal": 480},
                "frameRate": {"ideal": 15},
            },
        )
        conn_status = gr.Markdown(visible=False)
        load_ts = gr.State(0.0)
        demo.load(lambda: time.time(), outputs=load_ts)
        watchdog_timer = gr.Timer(2)
        watchdog_timer.tick(connection_watchdog, inputs=[name_box, load_ts], outputs=[conn_status, load_ts])
        webrtc.stream(fn=video_handler, inputs=[webrtc, name_box], outputs=[webrtc], time_limit=1800)

    with gr.Tab("Presenter"):
        gr.Markdown("Pick a connected phone to show full-screen while screen-sharing.")
        with gr.Row():
            device_dd = gr.Dropdown(choices=[], label="Device", interactive=True)
        presenter_img = gr.Image(label="Live", interactive=False, show_label=False)
        status_md = gr.Markdown()
        list_timer = gr.Timer(2)
        list_timer.tick(refresh_device_dropdown, inputs=device_dd, outputs=device_dd)
        frame_timer = gr.Timer(0.2)
        frame_timer.tick(presenter_frame, inputs=device_dd, outputs=[presenter_img, status_md])


if __name__ == "__main__":
    demo.queue().launch(
        server_name=HOST,
        server_port=PORT,
        show_error=True,
        share=False,
        inbrowser=False,
    )
