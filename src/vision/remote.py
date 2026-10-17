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
import html
import io
import os
import sys
import threading
import time

import gradio as gr
from PIL import Image


def _log(msg: str) -> None:
    print(f"[remote] {msg}", file=sys.stderr, flush=True)

DEVICE_TTL_S = float(os.environ.get("DEVICE_TTL_S", "30"))  # devices idle longer than this are dropped
MAX_FRAME_SIDE = 480  # phone frames are downscaled to this many px on the long side
# ~5 fps by default; override with env vars if the network/CPU needs a different budget.
PHONE_STREAM_INTERVAL_S = float(os.environ.get("PHONE_STREAM_INTERVAL_S", "0.2"))
PRESENTER_REFRESH_S = float(os.environ.get("PRESENTER_REFRESH_S", "0.2"))
JPEG_QUALITY = 75

_lock = threading.Lock()
_devices: dict[str, dict] = {}
_infer_busy = threading.Lock()  # held during a single classification; new frames are skipped while held


def _downscale(image: Image.Image, max_side: int = MAX_FRAME_SIDE) -> Image.Image:
    img = image.copy()
    img.thumbnail((max_side, max_side), Image.Resampling.BILINEAR)
    return img.convert("RGB")


def _data_uri(image: Image.Image, quality: int = JPEG_QUALITY) -> str:
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
    _log(f"_register_frame: name={name!r} size={image.size} label={result['label']!r}")


_PLACEHOLDER_RESULT = {
    "label": "Waiting...",
    "confidence": 0.0,
    "probabilities": {},
    "is_uncertain": True,
    "latency_ms": 0.0,
}


def _register_join(name: str) -> None:
    """Puts a placeholder entry in the registry as soon as someone joins, so their
    name shows in the Presenter dropdown even before their first frame arrives."""
    with _lock:
        if name not in _devices:
            _devices[name] = {"image": None, "result": dict(_PLACEHOLDER_RESULT), "last_seen": time.monotonic()}
    _log(f"_register_join: name={name!r}")


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
    name = html.escape(name)
    return (
        f'<p style="margin:4px 0; font-size:1.1em;">{name}: '
        f'<strong style="color:{color};">{result["label"]}</strong> '
        f'&middot; {result["confidence"] * 100:.1f}% '
        f'<span style="color:#6b7280;">({result["latency_ms"]:.0f} ms)</span></p>'
    )


def _large_card_html(name: str, device: dict) -> str:
    result = device["result"]
    color = "#d97706" if result["is_uncertain"] else "#15803d"
    name = html.escape(name)
    if device.get("image") is None:
        img_html = (
            '<div style="width:100%; max-height:58vh; aspect-ratio:4/3; border-radius:10px; background:#f3f4f6; '
            'display:flex; align-items:center; justify-content:center; color:#9ca3af; '
            'font-size:1.3em;">Waiting for a photo...</div>'
        )
    else:
        thumb = _data_uri(_downscale(device["image"], max_side=960))
        img_html = (
            f'<img src="{thumb}" style="max-width:100%; max-height:58vh; width:auto; height:auto; '
            f'object-fit:contain; border-radius:10px; display:block;"/>'
        )
    return f"""
    <div style="display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; width:100%;">
      <div style="flex:1 1 55%; min-width:280px; max-height:58vh; display:flex; align-items:center; justify-content:center;">
        {img_html}
      </div>
      <div style="flex:1 1 320px; min-width:260px;">
        <p style="margin:0 0 2px 0; font-size:1em; color:#6b7280;">{name}</p>
        <p style="margin:0 0 10px 0; font-size:1.8em; font-weight:700; color:{color}; line-height:1.15;">
          {result["label"]} &middot; {result["confidence"] * 100:.1f}%
          <span style="color:#6b7280; font-weight:400; font-size:0.45em; display:block;">({result["latency_ms"]:.0f} ms)</span>
        </p>
        {_bars_html(result["probabilities"])}
      </div>
    </div>
    """


def _grid_html(devices: dict) -> str:
    if not devices:
        return "<p>No phones connected yet. Share the link and open the Phone camera tab.</p>"
    cards = []
    for name, device in sorted(devices.items()):
        result = device["result"]
        color = "#d97706" if result["is_uncertain"] else "#15803d"
        safe_name = html.escape(name)
        if device.get("image") is None:
            thumb_html = (
                '<div style="width:100%; height:100%; min-height:140px; border-radius:8px; '
                'background:#f3f4f6; display:flex; align-items:center; justify-content:center; '
                'color:#9ca3af; font-size:1.1em;">Waiting for a photo...</div>'
            )
        else:
            thumb = _data_uri(_downscale(device["image"], max_side=640))
            thumb_html = f'<img src="{thumb}" style="max-width:100%; max-height:100%; object-fit:contain; border-radius:8px;"/>'
        cards.append(
            f"""
            <div style="flex:1 1 28%; min-width:240px; max-width:32%; max-height:46vh; display:flex; flex-direction:column; border:1px solid #e5e7eb; border-radius:10px; padding:12px;">
              <div style="flex:1 1 auto; min-height:0; display:flex; align-items:center; justify-content:center; overflow:hidden;">
                {thumb_html}
              </div>
              <p style="margin:8px 0 2px 0; font-size:1em; color:#6b7280; word-break:break-all;">{safe_name}</p>
              <p style="margin:0; font-weight:700; font-size:1.4em; color:{color};">
                {result["label"]} &middot; {result["confidence"] * 100:.1f}%
              </p>
            </div>
            """
        )
    return f'<div style="display:flex; flex-wrap:wrap; gap:14px; align-items:flex-start;">{"".join(cards)}</div>'


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
    rear_camera = gr.WebcamOptions(constraints={"facingMode": {"ideal": "environment"}})
    cam = gr.Image(
        sources=["webcam"],
        streaming=True,
        type="pil",
        label="Point at an object (live stream)",
        visible=False,
        webcam_options=rear_camera,
    )
    with gr.Row(visible=False) as flash_row:
        flash_btn = gr.Button("Flash: off", elem_id="flash-toggle-btn")
        flash_status = gr.HTML(elem_id="flash-status")
    gr.Markdown(
        "If the live stream above doesn't start (common on some phone browsers "
        "through the proxy), use this instead:",
        visible=True,
    )
    upload = gr.Image(
        sources=["upload", "webcam"],
        type="pil",
        label="Or take / upload a photo",
        visible=False,
        webcam_options=rear_camera,
    )
    send_btn = gr.Button("Send photo", variant="primary", visible=False)
    result_out = gr.HTML()

    def join(name):
        name = (name or "").strip()
        if not name:
            return (
                gr.update(), "", gr.update(visible=False), gr.update(visible=False),
                gr.update(visible=False), gr.update(visible=False), "",
            )
        _register_join(name)
        _log(f"join: name={name!r}")
        return (
            gr.update(value=name, interactive=False),
            name,
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True),
            "",
        )

    join_btn.click(
        join,
        inputs=name_box,
        outputs=[name_box, name_state, cam, flash_row, upload, send_btn, result_out],
    )

    # Toggles the rear camera's torch directly via the page's MediaStreamTrack, entirely
    # client-side (no round trip to the server). Finds the <video> element feeding the live
    # stream, flips its track's torch constraint, and falls back to a status note when the
    # browser/device doesn't expose torch control (common on iOS Safari).
    flash_btn.click(
        fn=None,
        inputs=None,
        outputs=None,
        js="""
        () => {
            const statusEl = document.getElementById('flash-status');
            const btn = document.getElementById('flash-toggle-btn');
            const setStatus = (msg) => { if (statusEl) statusEl.innerHTML = msg ? `<p style="margin:4px 0;color:#6b7280;font-size:0.9em;">${msg}</p>` : ''; };
            const video = Array.from(document.querySelectorAll('video')).find(v => v.srcObject && v.readyState >= 2);
            if (!video) { setStatus('Start the camera first.'); return; }
            const track = video.srcObject.getVideoTracks()[0];
            if (!track) { setStatus('No camera track found.'); return; }
            const caps = track.getCapabilities ? track.getCapabilities() : {};
            if (!caps.torch) {
                setStatus('Flash not supported on this phone; turn on a light.');
                return;
            }
            const turningOn = !(btn && btn.textContent.includes('on'));
            track.applyConstraints({ advanced: [{ torch: turningOn }] })
                .then(() => {
                    if (btn) btn.textContent = turningOn ? 'Flash: on' : 'Flash: off';
                    setStatus('');
                })
                .catch(() => setStatus('Could not toggle flash on this phone.'));
        }
        """,
    )

    def _classify_and_register(frame, name, label):
        if frame is None or not name:
            return gr.skip()
        small = _downscale(frame)
        if not _infer_busy.acquire(blocking=False):
            _log(f"{label}: busy, dropping frame for name={name!r}")
            return gr.skip()
        try:
            buf = io.BytesIO()
            small.save(buf, format="JPEG", quality=85)
            frame_bytes = buf.tell()
            result = classifier.predict(small)
        except Exception as exc:
            _log(f"{label}: predict failed name={name!r} err={exc!r}")
            return "<p style='color:#b91c1c;'>Could not read this camera frame.</p>"
        finally:
            _infer_busy.release()
        _log(
            f"{label}: name={name!r} frame_size={small.size} frame_bytes={frame_bytes} "
            f"classify_ms={result['latency_ms']:.1f} label={result['label']!r}"
        )
        _register_frame(name, small, result)
        return _own_card_html(name, result)

    def on_frame(frame, name):
        return _classify_and_register(frame, name, "on_frame")

    def on_send(frame, name):
        return _classify_and_register(frame, name, "on_send")

    cam.stream(on_frame, inputs=[cam, name_state], outputs=result_out, stream_every=PHONE_STREAM_INTERVAL_S)
    send_btn.click(on_send, inputs=[upload, name_state], outputs=result_out)


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
