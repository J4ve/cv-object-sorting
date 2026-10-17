# Dataset

## Source

[RealWaste](https://doi.org/10.24432/C5SS4G) — UC Irvine Machine Learning Repository, 2023
(CC BY 4.0). Single, S., Iranmanesh, S., & Raad, R. (2023). *RealWaste: A novel real-life
data set for landfill waste classification using deep learning.* Information, 14(12), Article 633.
https://doi.org/10.3390/info14120633

4,752 photographs of waste items taken at the point of reception at a landfill in Wollongong,
Australia, across 9 original material classes. Images are not committed to this repository —
`src/training/Midterm_Object_Sorting_RealWaste.ipynb` downloads the dataset zip directly from
UCI (`https://archive.ics.uci.edu/static/public/908/realwaste.zip`) at run time.

## Classes used (Midterm subset)

The group uses 5 of the 9 RealWaste classes, staying within the midterm limit of 3–5 classes.
The other 4 classes (Food Organics, Miscellaneous Trash, Textile Trash, Vegetation) are excluded.

| Class | Images |
|---|---|
| Cardboard | 461 |
| Glass | 420 |
| Metal | 790 |
| Paper | 500 |
| Plastic | 921 |
| **Total** | **3,092** |

All classes exceed the midterm minimum of 100 images per class.

## Train / validation / test split

Stratified 70/15/15 split (`sklearn.model_selection.train_test_split`, seed 42), done on raw file
paths before augmentation so no validation/test image is used in training.

| Split | Images | Percentage |
|---|---|---|
| Training | 2,164 | 70% |
| Validation | 464 | 15% |
| Testing | 464 | 15% |
| **Total** | **3,092** | 100% |

Per-class counts are in `src/training/Midterm_Object_Sorting_RealWaste.ipynb` (Step 3) and the
project report (`docs/`, Table 1 / Section 3.5).

- **Training set** — used to fit the CNN's weights.
- **Validation set** — used for early stopping / learning-rate reduction during training; not
  used to update weights directly.
- **Testing set** — held out and evaluated once at the end (Step 6 of the notebook) to report
  accuracy, precision/recall/F1 and the confusion matrix.

## Preprocessing

- Resize to 224×224, decode as RGB (`tf.io.decode_image`), pixel values rescaled to the
  MobileNetV2 input range inside the model (`Rescaling(1/127.5, offset=-1)`).
- Training-only augmentation: random horizontal/vertical flip, rotation (±15%), zoom (±15%),
  brightness (±20%), contrast (±20%).

## Final-stage placeholder

*Final-only, not part of the Midterm submission.* The Final dataset requirements (5 required
classes, 150+ samples/class, 50+ unseen real-world test images) are not addressed here.
