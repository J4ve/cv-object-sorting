# Models

## Architecture

MobileNetV2 (pre-trained on ImageNet, `include_top=False`, 224×224×3 input) as a frozen
feature extractor, followed by:

- `GlobalAveragePooling2D`
- `Dropout(0.3)`
- `Dense(5, activation='softmax')`

Trained in two stages (`src/training/Midterm_Object_Sorting_RealWaste.ipynb`, Step 5):

1. **Head training** — base frozen, Adam (lr 1e-3), 12 epochs, class-weighted
   sparse categorical cross-entropy.
2. **Fine-tuning** — last 40 layers of MobileNetV2 unfrozen (BatchNorm layers kept frozen),
   Adam (lr 1e-5), 10 epochs.

`EarlyStopping` (patience 4, `restore_best_weights=True`) and `ReduceLROnPlateau`
(patience 2, factor 0.5) monitor validation loss in both stages.

## Classes (fixed order)

```
['Cardboard', 'Glass', 'Metal', 'Paper', 'Plastic']
```

Predictions are the softmax argmax over this exact order; a prediction below 0.60 confidence
is reported as "Uncertain" rather than forced into a class.

## Model file / access

**Placeholder — not yet populated.** The notebook run that produced the reported 88.15% test
accuracy (`src/training/Midterm_Object_Sorting_RealWaste.ipynb`, Step 8) saved
`waste_classifier.keras` to the Colab session, but that file was not exported from Colab and
is not present in the group's submitted materials. No trained weights are committed to this
repository yet. See `src/vision/README.md` for the live-demo owner's plan to retrain and
export weights here.

## Loading the model (once weights are added)

```python
from tensorflow import keras
model = keras.models.load_model('models/waste_classifier.keras')
```

Preprocess inputs exactly as in the notebook (RGB, resize to 224×224, float32 — rescaling to
[-1, 1] is baked into the model) and index predictions against the class list above.
