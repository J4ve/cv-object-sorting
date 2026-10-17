"""Reproduces the RealWaste waste-classifier pipeline from the Midterm Colab notebook
(Midterm_Object_Sorting_RealWaste.ipynb) outside Colab, and exports the trained model
for the local demo in src/vision/.

Same dataset subset, same stratified split (seed=42), same preprocessing, same
MobileNetV2 two-stage transfer-learning setup, same class weighting, as the notebook.

Usage:
    python src/training/train_export.py
"""
import json
import os
import random
import shutil
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from tensorflow import keras
from tensorflow.keras import layers

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw_data"
MODELS_DIR = REPO_ROOT / "models"
RESULTS_DIR = REPO_ROOT / "results"

CLASSES = ["Cardboard", "Glass", "Metal", "Paper", "Plastic"]
SPLIT = (0.70, 0.15, 0.15)  # train / validation / test
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
SEED = 42
EPOCHS_HEAD = 12
EPOCHS_FT = 10
WEIGHTS = "imagenet"
UCI_URL = "https://archive.ics.uci.edu/static/public/908/realwaste.zip"

random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)


def ensure_dataset() -> Path:
    """Downloads and extracts the RealWaste zip into data/raw_data if not already present."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DATA_DIR / "realwaste.zip"
    if not RAW_DIR.exists() or not any(RAW_DIR.rglob("*")):
        if not zip_path.exists():
            print(f"Downloading dataset from {UCI_URL} ...")
            import urllib.request

            urllib.request.urlretrieve(UCI_URL, zip_path)
        assert zipfile.is_zipfile(zip_path), f"Not a valid zip file: {zip_path}"
        shutil.rmtree(RAW_DIR, ignore_errors=True)
        RAW_DIR.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(RAW_DIR)
        for inner in list(RAW_DIR.rglob("*.zip")):
            with zipfile.ZipFile(inner) as z:
                z.extractall(inner.parent / (inner.stem + "_x"))
        print("Extracted.")
    return RAW_DIR


IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def images_in(folder):
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMG_EXT)


def collect_class_images(raw_dir: Path):
    found = {}
    for d in raw_dir.rglob("*"):
        if d.is_dir() and "__MACOSX" not in d.parts:
            for cls in CLASSES:
                if d.name.strip().lower() == cls.lower():
                    n = len(images_in(d))
                    if n and n > len(found.get(cls, [])):
                        found[cls] = images_in(d)
    missing = [c for c in CLASSES if c not in found]
    assert not missing, f"Could not find image folders for: {missing}"
    counts = pd.Series({c: len(found[c]) for c in CLASSES}, name="images")
    assert counts.min() >= 100, "Midterm requires at least 100 samples per class"
    return found, counts


def make_splits(found):
    paths = [str(p) for c in CLASSES for p in found[c]]
    labels = [CLASSES.index(c) for c in CLASSES for _ in found[c]]

    p_tr, p_tmp, y_tr, y_tmp = train_test_split(
        paths, labels, test_size=SPLIT[1] + SPLIT[2], stratify=labels, random_state=SEED
    )
    p_va, p_te, y_va, y_te = train_test_split(
        p_tmp, y_tmp, test_size=SPLIT[2] / (SPLIT[1] + SPLIT[2]), stratify=y_tmp, random_state=SEED
    )
    assert not (set(p_tr) & set(p_va) or set(p_tr) & set(p_te) or set(p_va) & set(p_te)), "Leak between sets!"
    return (p_tr, y_tr), (p_va, y_va), (p_te, y_te)


AUTOTUNE = tf.data.AUTOTUNE


def load_image(path, label):
    img = tf.io.read_file(path)
    img = tf.io.decode_image(img, channels=3, expand_animations=False)
    img = tf.image.resize(img, IMG_SIZE, antialias=True)
    img.set_shape((*IMG_SIZE, 3))
    return img, label


def make_ds(p, y, shuffle=False):
    ds = tf.data.Dataset.from_tensor_slices((p, np.array(y, dtype=np.int32)))
    if shuffle:
        ds = ds.shuffle(len(p), seed=SEED, reshuffle_each_iteration=True)
    return ds.map(load_image, num_parallel_calls=AUTOTUNE).batch(BATCH_SIZE).prefetch(AUTOTUNE)


augment = keras.Sequential(
    [
        layers.RandomFlip("horizontal_and_vertical"),
        layers.RandomRotation(0.15),
        layers.RandomZoom(0.15),
        layers.RandomBrightness(0.2, value_range=(0, 255)),
        layers.RandomContrast(0.2),
    ],
    name="augmentation",
)


def build_model(num_classes):
    inputs = keras.Input(shape=(*IMG_SIZE, 3))
    x = augment(inputs)
    x = layers.Rescaling(1 / 127.5, offset=-1)(x)
    base = keras.applications.MobileNetV2(input_shape=(*IMG_SIZE, 3), include_top=False, weights=WEIGHTS)
    base.trainable = False
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)
    return keras.Model(inputs, outputs), base


def main():
    print("TensorFlow", tf.__version__)
    gpus = tf.config.list_physical_devices("GPU")
    print("GPU:", gpus if gpus else "none (training on CPU)")

    raw_dir = ensure_dataset()
    found, counts = collect_class_images(raw_dir)
    print(counts.to_string())

    (p_tr, y_tr), (p_va, y_va), (p_te, y_te) = make_splits(found)
    print(f"Split: {len(p_tr)} train / {len(p_va)} val / {len(p_te)} test")

    train_ds = make_ds(p_tr, y_tr, shuffle=True)
    val_ds = make_ds(p_va, y_va)
    test_ds = make_ds(p_te, y_te)

    model, base = build_model(len(CLASSES))
    cw = compute_class_weight("balanced", classes=np.arange(len(CLASSES)), y=np.array(y_tr))
    class_weight = dict(enumerate(cw))
    print("class weights:", {CLASSES[k]: round(v, 2) for k, v in class_weight.items()})

    callbacks = [
        keras.callbacks.EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=2, verbose=1),
    ]

    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    t0 = time.time()
    model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS_HEAD, class_weight=class_weight, callbacks=callbacks)
    print(f"Stage 1 done in {(time.time() - t0) / 60:.1f} min")

    base.trainable = True
    for layer in base.layers[:-40]:
        layer.trainable = False
    for layer in base.layers:
        if isinstance(layer, layers.BatchNormalization):
            layer.trainable = False

    model.compile(optimizer=keras.optimizers.Adam(1e-5), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    t0 = time.time()
    model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS_FT, class_weight=class_weight, callbacks=callbacks)
    print(f"Stage 2 done in {(time.time() - t0) / 60:.1f} min")

    probs = model.predict(test_ds, verbose=0)
    y_pred = probs.argmax(1)
    y_true = np.array(y_te)
    test_acc = accuracy_score(y_true, y_pred)
    print(f"TEST ACCURACY: {test_acc * 100:.2f}%  ({(y_true == y_pred).sum()} of {len(y_true)} images correct)")

    rep = classification_report(y_true, y_pred, target_names=CLASSES, output_dict=True, digits=4, zero_division=0)
    print(f"Macro F1: {rep['macro avg']['f1-score']:.4f} | Weighted F1: {rep['weighted avg']['f1-score']:.4f}")

    cm = confusion_matrix(y_true, y_pred)
    print("Confusion matrix (rows=true, cols=pred, order=" + ", ".join(CLASSES) + "):")
    print(cm)
    cm = cm.tolist()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    model.save(MODELS_DIR / "waste_classifier.keras")
    json.dump(CLASSES, open(MODELS_DIR / "class_names.json", "w"))

    results = {
        "classes": CLASSES,
        "images_per_class": counts.to_dict(),
        "split": {"train": len(p_tr), "val": len(p_va), "test": len(p_te)},
        "test_accuracy": round(float(test_acc), 4),
        "macro_f1": round(rep["macro avg"]["f1-score"], 4),
        "weighted_f1": round(rep["weighted avg"]["f1-score"], 4),
        "per_class_f1": {c: round(rep[c]["f1-score"], 4) for c in CLASSES},
        "classification_report": rep,
        "confusion_matrix": cm,
        "notebook_reference_test_accuracy": 0.8815,
        "notebook_reference_macro_f1": 0.8813,
    }
    json.dump(results, open(RESULTS_DIR / "results.json", "w"), indent=2)
    print(json.dumps(results, indent=2))

    weights_mb = os.path.getsize(MODELS_DIR / "waste_classifier.keras") / 1e6
    print(f"Saved model: {weights_mb:.1f} MB")
    if weights_mb > 90:
        print("NOTE: weights file exceeds ~90 MB, keep it out of git (see .gitignore / models/README.md).")


if __name__ == "__main__":
    main()
