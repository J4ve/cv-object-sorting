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

Predictions are the softmax argmax over this exact order; a prediction below 0.60 confidence
is reported as "Uncertain" rather than forced into a class.

## Model file / access

**Not yet populated.** The report (`docs/`) cites 87.93% test accuracy, from a separate local
run of this same pipeline whose weights file (`waste_classifier.keras`) has not been placed in
this repository yet. A different notebook run saved to a Colab session (88.15% test accuracy,
not the number in the report) was also never exported from Colab. No trained weights are
committed here yet; they will be added once the live demo (`src/vision/README.md`) retrains
and exports the model that matches the report's numbers.

## Loading the model (once weights are added)

```python
from tensorflow import keras
model = keras.models.load_model('models/waste_classifier.keras')
```

Preprocess inputs exactly as in the notebook (RGB, resize to 224x224, float32; rescaling to
[-1, 1] is baked into the model) and index predictions against the class list above.
