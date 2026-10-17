# Models

## Architecture

MobileNetV2 (pre-trained on ImageNet, `include_top=False`, 224x224x3 input) as a frozen
feature extractor, followed by:

- `GlobalAveragePooling2D`
- `Dropout(0.3)`
- `Dense(5, activation='softmax')`

Trained in two stages (`src/training/Midterm_Object_Sorting_RealWaste.ipynb`, Step 5):

1. **Head training:** base frozen, Adam (lr 1e-3), 12 epochs, class-weighted
   sparse categorical cross-entropy.
2. **Fine-tuning:** last 40 layers of MobileNetV2 unfrozen (BatchNorm layers kept frozen),
   Adam (lr 1e-5), 10 epochs.

`EarlyStopping` (patience 4, `restore_best_weights=True`) and `ReduceLROnPlateau`
(patience 2, factor 0.5) monitor validation loss in both stages.

## Classes (fixed order)

```
['Cardboard', 'Glass', 'Metal', 'Paper', 'Plastic']
```

Predictions are the softmax argmax over this exact order; a prediction below that predicted
class's own confidence threshold is reported as "Uncertain" rather than forced into a class.
Thresholds are per class (`class_thresholds.json`, below), selected on the validation set with
a global fallback of 0.59; see `results/class_thresholds.json` and
`results/threshold_selection.json` for the selection data.

## Per-class confidence thresholds

`class_thresholds.json` holds one confidence threshold per class, e.g. `{"Cardboard": 0.64,
"Glass": 0.58, "Metal": 0.52, "Paper": 0.55, "Plastic": 0.6}`. For each class, it's the
smallest threshold where validation precision among kept predictions reaches 90% (falling
back to the global threshold, 0.59, when a class has too few validation predictions or never
reaches 90%). Produced by `src/training/Midterm_Object_Sorting_RealWaste.ipynb` (Step 6g);
full selection data, including any fallbacks and the test-set check, is in
`results/class_thresholds.json`.

## Model file / access

`waste_classifier.keras` and `class_names.json` are committed in this folder, produced by
`src/training/train_export.py` (a local reproduction of
`src/training/Midterm_Object_Sorting_RealWaste.ipynb`'s exact pipeline). See
`results/results.json` for the reproduced test accuracy, macro F1, and confusion matrix from
that run.

If the weights are missing or you want to retrain, regenerate them with:

```bash
python src/training/train_export.py
```

This downloads the RealWaste dataset into a gitignored `data/` folder and writes both files
here plus `results/results.json`.

## Loading the model

```python
from tensorflow import keras
model = keras.models.load_model('models/waste_classifier.keras')
```

Preprocess inputs exactly as in the notebook (RGB, resize to 224x224, float32; rescaling to
[-1, 1] is baked into the model) and index predictions against the class list above.

## Size note

The MobileNetV2-based `.keras` export is in the ~10-25 MB range, well under GitHub's limits,
so it is committed directly. If a future retrain produces a file over ~90 MB, keep it out of
git (add a `*.keras` exclusion override) and note the external location here instead.
