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
