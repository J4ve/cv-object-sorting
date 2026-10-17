# Models

Trained weights for the RealWaste 5-class waste classifier, produced by
`src/training/train_export.py` (reproduces
`src/training/Midterm_Object_Sorting_RealWaste.ipynb`).

- `waste_classifier.keras` - MobileNetV2 (ImageNet) transfer-learning model,
  two-stage trained (head, then fine-tuned last 40 layers with BatchNorm
  frozen). Input: 224x224 raw 0-255 RGB (the model itself rescales to
  [-1, 1]).
- `class_names.json` - ordered list of the 5 class names the model's output
  indices correspond to: `["Cardboard", "Glass", "Metal", "Paper", "Plastic"]`.

## Getting the weights

If `waste_classifier.keras` is not present in this folder (it is gitignored
whenever it exceeds GitHub's practical size budget, see note below), generate
it locally:

```bash
python src/training/train_export.py
```

This downloads the RealWaste dataset into a gitignored `data/` folder,
reproduces the notebook's exact pipeline and two-stage training, and writes
both files here plus `results/results.json` with the reproduced metrics.

## Size note

MobileNetV2-based `.keras` export is typically in the 10-20 MB range, well
under GitHub's limits, so it is committed directly. If a future retrain
produces a file over ~90 MB, keep it out of git (it is already covered by a
`*.keras` rule if you add one) and note the external location here instead.
