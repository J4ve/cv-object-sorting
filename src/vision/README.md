# Waste classifier - local live demo

Midterm "SEE and RECOGNIZE" demonstration for the RealWaste 5-class waste
classifier (Cardboard, Glass, Metal, Paper, Plastic). Upload images or take a
live webcam snapshot and see the predicted class, confidence, and top-3
probabilities side by side with the image.

Robot integration (deciding a sorting destination and acting on it with a 4WD
robot) is planned for the Final project. `src/vision/classifier.py` is a
standalone inference module with no UI code, so the Final project's robot
SEE-DECIDE-ACT loop can import `WasteClassifier` directly.

## Setup

From the repo root, run the one-command setup script (creates `.venv`,
installs pinned dependencies, registers a Jupyter kernel, checks GPU
visibility):

```bash
./scripts/setup_env.sh
source .venv/bin/activate
```

See the repo root `requirements.txt` and `.python-version` for exact pins.

## Get the trained model

The demo needs `models/waste_classifier.keras` and `models/class_names.json`.
If they are not already present (the `.keras` weights file is gitignored
when it is large, see `models/README.md`), train and export them first:

```bash
python src/training/train_export.py
```

This downloads the RealWaste dataset into a gitignored `data/` folder,
reproduces the notebook's training pipeline, and writes the model files plus
`results/results.json`.

## Run the demo

```bash
python src/vision/app.py
```

Serves on `http://127.0.0.1:7860`. Open it in a browser:

- **Upload / batch** tab: drag and drop one or more images; each gets a
  gallery card with its predicted label, plus a markdown block below with
  confidence and the top-3 class probabilities.
- **Live camera** tab: take a webcam snapshot; it is classified the same way.

The model is loaded once at startup and warmed up with one dummy inference,
so the first real prediction is not slowed by lazy initialization. Odd or
corrupt image files are caught per-image and reported in the UI instead of
crashing the server.

Stop the server with Ctrl+C.

## Remote / phone demo

The **Phone camera** and **Presenter** tabs let groupmates join from their
own phones over a public tunnel during a screen-shared presentation. See
[`docs/remote-demo.md`](../../docs/remote-demo.md) for how to start the
tunnel, the URL to share, and how to stop it.

## Sample images

`src/vision/samples/` has one small (resized to 512px max side) example image
per class for one-click testing in the Upload tab. They come from the
RealWaste dataset: Single, S., & Iranmanesh, S. (University of Wollongong),
*RealWaste* [Data set]. The dataset's authors license it CC BY-NC-SA 4.0 (the
UCI mirror lists CC BY 4.0; we follow the more restrictive author license).
Only these few small sample images are committed here for demo convenience;
the full dataset itself is never committed.

## Demo tips

The model is trained on RealWaste's landfill-sorted photos, so accuracy can
drop on clean, new-looking objects (a large domain shift from landfill items
to pristine ones). For the most reliable live results:
- Use real, used, or slightly crumpled items in plain, even light.
- If unsure, start with the one-click RealWaste sample images to see a
  confident, correct prediction first.
- A result labeled "Uncertain" means the model's top confidence was too low
  to trust; try a different angle or lighting rather than treating it as a
  wrong class.
