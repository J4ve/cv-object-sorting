# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Captain framing rule: Midterm done, robot planned

This repo is a Midterm-only submission for a Visual Object Sorting 4WD robot project
(Group Specialization 8). Two kinds of content coexist in the README, every sub-README, and
the report, and must be worded differently:

- **Midterm Computer Vision work (dataset, model, training, evaluation, demo)** is presented
  as completed work, not a placeholder.
- **Robot parts (4WD chassis, motors, motor driver, controller, the SEE -> DECIDE -> ACT loop,
  Test 1, Test 2)** are presented as "Planned for the Final project," with a short description
  of the intended design. Never word them as done, and never leave them as a bare empty
  placeholder with no description.

In the report (`docs/*.docx`, `docs/*.pdf`) the Computer Vision Project Report Format
template overrides this: sections marked "Final Project only" in the template (2.5, 5.4, 5.5,
6.6, 6.7, 7.4, 7.5) are removed from the Midterm report entirely, not filled in and not
described as planned. The planned robot work is mentioned only briefly, in 1.4 (Scope and
Limitations) and 9.2 (Recommendations).

## Writing style

No em dashes in any prose (README files, report text, this file). Use a period, comma, colon,
or parentheses instead. US English spelling.

## FastRTC (experimental WebRTC demo, src/vision/webrtc_app.py)

- `fastrtc` pins `gradio<6.0`; it cannot share a venv with `app.py`'s `gradio==6.30.0`.
  Pin `tensorflow`/`numpy` to the versions in `requirements.txt` when installing fastrtc so
  pip resolves a compatible `gradio` (5.50.0 as of this writing) without re-downloading TF.
- The `WebRTC` gradio component's `VideoCallback.recv()` blocks forever on
  `wait_for_channel()` until the client opens an `RTCDataChannel`. FastRTC's own JS frontend
  always does this; a raw client (e.g. `aiortc` for headless testing, see
  `scripts/webrtc_client_test.py`) must call `pc.createDataChannel(...)` before `createOffer()`
  or no video frame is ever processed.
- Signaling for the gradio `WebRTC` component goes through gradio's generic
  `/gradio_api/component_server` RPC (`fn_name: "offer"`), not a dedicated `/webrtc/offer`
  route; that route only exists when using `fastrtc.Stream.mount()` directly, not inside
  `gr.Blocks`.
- A VPS `caddy reload` is not disruption-free: it briefly cuts long-held
  `/gradio_api/stream/...` long-polls (observed ~10-15s of 502s on the primary demo during an
  unrelated reload). Gradio's client reconnects on its own, but avoid reloading Caddy while a
  real demo session may be live.

## Report docx and PDF (docs/Midterm - Computer Vision Project Report.*)

- The committed docx is produced by `scripts/restyle_report.py`, which reads the pre-restyle
  Google Docs export and rewrites its paragraph and table properties. It is a one-shot
  migration, not a formatter: it renumbers tables and figures from their original numbers,
  so it must run against the docx as it stood before the restyle (commit a65b549) and it
  refuses to run on its own output.
- Regenerate the PDF with
  `soffice -env:UserInstallation=file://<scratch>/lo_profile --headless --convert-to pdf`.
  Without the private profile a desktop LibreOffice session makes the headless convert
  silently do nothing.
- Every figure that carries data must come from an executed notebook cell (captain rule).
  The dataset distribution chart is a Step 3 cell of
  `src/training/Midterm_Object_Sorting_RealWaste.ipynb`; only the architecture block
  diagram is drawn outside it, by `docs/images/make_architecture_figure.py`.
- OOXML gotchas this document hit: `w:ind` values are twips, while python-docx reports them
  as EMU, so reading a value and writing it back silently indents by inches; the Google Docs
  export carried an invalid non-integer `w:line` spacing value, which is what made the first
  section heading render clipped in Word; and `w:sectPr` must stay the last child of the
  body, so appended content goes in with `sectPr.addprevious(...)`.
- The docx still carries one Google Docs review comment on the title. It does not appear in
  the PDF. Removing it is the captain's call, not a worker's.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
