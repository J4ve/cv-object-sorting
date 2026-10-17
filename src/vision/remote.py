"""Phone-camera and presenter tabs for presenting the demo over Google Meet.

Groupmates open the "Phone camera" tab on their own phone (over the app's
``--share`` link), enter a display name once, and stream downscaled
snapshots from the phone's camera. The presenter uses the "Presenter" tab
to pick any connected phone from a dropdown (or "All devices" for a grid)
and shows its latest frame and prediction live on the shared screen.

State lives in one thread-safe in-memory dict keyed by device name
(``_devices`` below); nothing here is written to disk. Entries idle for
more than ``DEVICE_TTL_S`` are dropped automatically.
"""
import base64
import io
import threading
import time

import gradio as gr
from PIL import Image

DEVICE_TTL_S = 30.0  # devices idle longer than this are dropped from the registry
MAX_FRAME_SIDE = 320  # phone frames are downscaled to this many px on the long side
PHONE_STREAM_INTERVAL_S = 0.6  # ~1.6 frames/sec, within the spec's 1-2/sec budget
PRESENTER_REFRESH_S = 0.7  # presenter dropdown + display refresh interval

_lock = threading.Lock()
_devices: dict[str, dict] = {}


def _downscale(image: Image.Image, max_side: int = MAX_FRAME_SIDE) -> Image.Image:
    img = image.copy()
    img.thumbnail((max_side, max_side), Image.Resampling.BILINEAR)
    return img.convert("RGB")


def _data_uri(image: Image.Image, quality: int = 70) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _register_frame(name: str, image: Image.Image, result: dict) -> None:
    """Stores the latest frame + prediction for one device. Thread-safe: each
    call replaces the device's entry with a brand-new dict rather than
    mutating an existing one, so concurrent readers never see a half-written
    entry."""
    with _lock:
        _devices[name] = {
            "image": image,
            "result": result,
            "last_seen": time.monotonic(),
        }


def _prune_stale() -> None:
    cutoff = time.monotonic() - DEVICE_TTL_S
    with _lock:
        stale = [name for name, d in _devices.items() if d["last_seen"] < cutoff]
        for name in stale:
            del _devices[name]


def _snapshot_devices() -> dict:
    """A point-in-time copy of the registry, safe to read from outside the lock."""
    _prune_stale()
    with _lock:
        return dict(_devices)


def _bars_html(probabilities: dict, top_n: int = 3) -> str:
    top = sorted(probabilities.items(), key=lambda kv: -kv[1])[:top_n]
    rows = []
    for cls, p in top:
        pct = p * 100
        rows.append(
            f"""
            <div style="margin:4px 0;">
              <div style="display:flex; justify-content:space-between; font-size:0.85em;">
                <span>{cls}</span><span>{pct:.1f}%</span>
              </div>
              <div style="background:#e5e7eb; border-radius:4px; height:8px;">
                <div style="background:#4c78a8; width:{pct:.1f}%; height:8px; border-radius:4px;"></div>
              </div>
            </div>
            """
        )
    return "".join(rows)


def _own_card_html(name: str, result: dict) -> str:
    color = "#d97706" if result["is_uncertain"] else "#15803d"
    return (
        f'<p style="margin:4px 0; font-size:1.1em;">{name}: '
        f'<strong style="color:{color};">{result["label"]}</strong> '
        f'&middot; {result["confidence"] * 100:.1f}% '
        f'<span style="color:#6b7280;">({result["latency_ms"]:.0f} ms)</span></p>'
    )


def _large_card_html(name: str, device: dict) -> str:
    result = device["result"]
    color = "#d97706" if result["is_uncertain"] else "#15803d"
    thumb = _data_uri(_downscale(device["image"], max_side=480))
    return f"""
    <div>
      <img src="{thumb}" style="max-width:100%; border-radius:10px;"/>
      <p style="margin:10px 0 2px 0; font-size:0.9em; color:#6b7280;">{name}</p>
      <p style="margin:0 0 6px 0; font-size:1.3em; font-weight:600; color:{color};">
        {result["label"]} &middot; {result["confidence"] * 100:.1f}%
        <span style="color:#6b7280; font-weight:400; font-size:0.8em;">({result["latency_ms"]:.0f} ms)</span>
      </p>
      {_bars_html(result["probabilities"])}
    </div>
    """


def _grid_html(devices: dict) -> str:
    if not devices:
        return "<p>No phones connected yet. Share the link and open the Phone camera tab.</p>"
    cards = []
    for name, device in sorted(devices.items()):
        result = device["result"]
        color = "#d97706" if result["is_uncertain"] else "#15803d"
        thumb = _data_uri(_downscale(device["image"], max_side=220))
        cards.append(
            f"""
            <div style="width:220px; border:1px solid #e5e7eb; border-radius:8px; padding:8px;">
              <img src="{thumb}" style="width:100%; border-radius:6px;"/>
              <p style="margin:6px 0 2px 0; font-size:0.85em; color:#6b7280; word-break:break-all;">{name}</p>
              <p style="margin:0; font-weight:600; color:{color};">
                {result["label"]} &middot; {result["confidence"] * 100:.1f}%
              </p>
            </div>
            """
        )
    return f'<div style="display:flex; flex-wrap:wrap; gap:10px;">{"".join(cards)}</div>'


def build_phone_tab(classifier) -> None:
    """Builds the "Phone camera" tab contents in the currently-open gr.Tab/Blocks
    context. Call once per app, inside a `with gr.Tab("Phone camera"):` block
    (or any Blocks context)."""
    gr.Markdown(
        "### Phone camera\n"
        "Enter your name once, allow camera access, then point your phone's "
        "camera at an object. Your own label and confidence show below; the "
        "presenter can pick you from the **Presenter** tab's dropdown."
    )
    name_box = gr.Textbox(label="Your name", placeholder="e.g. Alex")
    join_btn = gr.Button("Start", variant="primary")
    name_state = gr.State("")
    cam = gr.Image(
        sources=["webcam"],
        streaming=True,
        type="pil",
        label="Point at an object",
        visible=False,
    )
    result_out = gr.HTML()

    def join(name):
        name = (name or "").strip()
        if not name:
            return gr.update(), "", gr.update(visible=False), "<p style='color:#b91c1c;'>Enter a name first.</p>"
        return gr.update(value=name, interactive=False), name, gr.update(visible=True), ""

    join_btn.click(join, inputs=name_box, outputs=[name_box, name_state, cam, result_out])

    def on_frame(frame, name):
        if frame is None or not name:
            return gr.skip()
        small = _downscale(frame)
        try:
            result = classifier.predict(small)
        except Exception:
            return "<p style='color:#b91c1c;'>Could not read this camera frame.</p>"
        _register_frame(name, small, result)
        return _own_card_html(name, result)

    cam.stream(on_frame, inputs=[cam, name_state], outputs=result_out, stream_every=PHONE_STREAM_INTERVAL_S)


def build_presenter_tab(classifier) -> None:
    """Builds the "Presenter" tab contents in the currently-open gr.Tab/Blocks
    context. `classifier` is accepted for a consistent signature with
    `build_phone_tab`, even though this tab only displays predictions the
    phones already computed."""
    del classifier  # predictions are computed on the phone side; this tab only displays them
    gr.Markdown(
        "### Presenter\n"
        "Pick a connected phone to show on screen, or show every connected "
        "phone at once with **All devices**."
    )
    device_dropdown = gr.Dropdown(choices=["All devices"], value="All devices", label="Device")
    display_out = gr.HTML()
    timer = gr.Timer(PRESENTER_REFRESH_S)

    def refresh_dropdown(current):
        devices = _snapshot_devices()
        choices = ["All devices"] + sorted(devices.keys())
        value = current if current in choices else "All devices"
        return gr.update(choices=choices, value=value)

    def render(selected):
        devices = _snapshot_devices()
        if not devices:
            return "<p>No phones connected yet. Share the link and open the Phone camera tab.</p>"
        if not selected or selected == "All devices":
            return _grid_html(devices)
        device = devices.get(selected)
        if device is None:
            return "<p>That device disconnected.</p>"
        return _large_card_html(selected, device)

    timer.tick(refresh_dropdown, inputs=device_dropdown, outputs=device_dropdown)
    timer.tick(render, inputs=device_dropdown, outputs=display_out)
