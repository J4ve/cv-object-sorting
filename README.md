# cv-object-sorting: Visual Object Sorting (RealWaste)

Computer Vision course Midterm-to-Final group project: a vision-based autonomous 4WD robot
assigned the **Object Sorting** specialization (Group Specialization 8). This repository is a
**Midterm** submission. The Computer Vision work (dataset, model, evaluation, demo) is
completed. The robot itself is planned for the Final project and described below as such, not
as finished work.

## Quick start (live demo on your machine)

_Owned by the `src/vision/` workstream; content lands with the demo._

## Project Title

Visual Object Sorting Robot: Computer Vision Midterm (RealWaste Waste Classification)

## Group Members

BS Computer Science, Section 4A

- Alba, John Raymond S.
- Bacsain, Jave A.
- Bagaporo, John Louie B.
- Nonato, Francis Gabriel F.
- Palacios, Harvey Lloyd V.
- Prestado, Marc Justin N.

## Assigned Group Project Specialization

**Specialization 8, Visual Object Sorting Robot.** The robot must identify objects from camera
images and route each to the correct category. Midterm requirement: recognize at least 4
object classes. This group uses **5** classes (Cardboard, Glass, Metal, Paper, Plastic),
exceeding the minimum.

## Project Description

Given an image or live camera frame of a single waste item, the system classifies it into one
of five material classes and displays the predicted label with a confidence score. This is the
completed Midterm deliverable. It is also the vision foundation the Final project will build
on: a robot that physically sorts the recognized item. At this stage the robot does not move;
only the recognition pipeline is built and evaluated.

## System Overview

- **Problem type:** multi-class image classification (one item per image; not
  detection/segmentation).
- **Approach:** transfer learning on a MobileNetV2 backbone pre-trained on ImageNet, fine-tuned
  on the RealWaste subset.
- **Pipeline (Midterm, completed):** `Input Image / Camera -> Preprocessing -> CNN Model ->
  Detection/Recognition -> Output (label + confidence)`.
- **Planned for the Final project:** the recognized class feeds a decision step that chooses a
  destination/action, which drives motor control so the robot physically sorts the item
  (`Camera -> CV -> Decision -> Robot Control -> Robot Action`, the SEE -> DECIDE -> ACT loop).

## Hardware Used

Completed (Midterm):

| Component | Specification / Model | Purpose |
|---|---|---|
| Camera | USB webcam, 720p (or laptop built-in camera) | Captures live frames of the object to recognize |
| Controller | Laptop/PC (Midterm) | Runs preprocessing and model inference |

**Planned for the Final project:** a 4WD chassis carries the sorting robot; an L298N dual
H-bridge motor driver drives 4 DC gear motors; an Arduino/ESP32 (or the same laptop/PC) runs the
decision logic and sends motor commands once the Computer Vision model identifies an object's
class.

## Software / Tools Used

| Software / Tool | Version | Purpose |
|---|---|---|
| Python | 3.11.9 | Main language for data prep, training, evaluation |
| TensorFlow | 2.21.0 | Deep learning framework (printed at notebook run time) |
| Keras | bundled with TensorFlow | Model building, training callbacks, saving |
| MobileNetV2 (Keras Applications) | ImageNet weights, 224x224, `include_top=False` | Pre-trained CNN backbone (transfer learning) |
| OpenCV (`opencv-python`) | 4.14.0 (printed at notebook run time) | Image I/O, color conversion, drawing the demo overlay |
| NumPy, pandas, Matplotlib, scikit-learn | see the training environment setup | Array math, tables, plots, metrics/splitting |

The group's submitted report lists OpenCV 5.0.0; the notebook's own printed output shows
4.14.0. The corrected report copy in `docs/` uses the printed version. Full audit:
`/media/jave/4CB2057BB2056AB2/firstmate/data/cv-demo/findings.md`.

**Planned for the Final project:** Arduino IDE, for the motor-control firmware.

## Computer Vision Methodology

Completed (Midterm):

1. Select the 5 classes from RealWaste and match each to its image folder.
2. Stratified 70/15/15 train/validation/test split (seed 42), done before augmentation.
3. Preprocess: decode as RGB, resize to 224x224, rescale to the MobileNetV2 input range.
4. Augment the training set only (flips, rotation, zoom, brightness, contrast).
5. Build MobileNetV2 (frozen) + GlobalAveragePooling2D + Dropout(0.3) + Dense(5, softmax).
6. Train in two stages: head-only (Adam 1e-3, 12 epochs, class-weighted loss), then fine-tune
   the last 40 backbone layers (Adam 1e-5, 10 epochs). `EarlyStopping` and `ReduceLROnPlateau`
   watch validation loss.
7. Evaluate once on the held-out test set: accuracy, per-class precision/recall/F1, confusion
   matrix.
8. Recognition/demo: same preprocessing, then model, then argmax, then label and confidence
   overlay. Predictions under 0.60 confidence are shown as "Uncertain".

**Planned for the Final project:** convert the recognized class into a sort decision and a
motor command sequence for the robot.

## Dataset Overview

Full documentation in [`dataset/README.md`](dataset/README.md). Summary: RealWaste (UCI ML
Repository, CC BY 4.0), 5 of its 9 classes used, 3,092 images total, stratified 70/15/15 split
(2,164 / 464 / 464).

## Model / Algorithm Used

MobileNetV2 transfer learning, as described above. Full documentation, class order, and
loading instructions in [`models/README.md`](models/README.md).

## System Architecture / Workflow

```
Completed (Midterm):
Input Image / Camera -> Preprocessing (resize 224x224, RGB) -> MobileNetV2 + classifier head
-> Softmax prediction -> Confidence check (>= 0.60?) -> Class label / "Uncertain" -> Visual output

Planned for the Final project:
Camera -> Computer Vision (above) -> Decision (choose destination) -> Robot Control (motor
driver) -> Robot Action (move/sort the item)
```

## Installation and Setup Instructions

The training/evaluation environment and the live demo app's setup script are owned by the
`src/vision/` workstream; see `src/vision/README.md` for the setup command once that work
lands (it will cover the shared Python environment used by both `src/training/` and
`src/vision/`).

## Instructions for Running the System

- **Training / evaluation notebook:** run
  `src/training/Midterm_Object_Sorting_RealWaste.ipynb` top to bottom (Colab recommended, GPU
  runtime). It reproduces dataset preparation, training, and the Step 6 evaluation (accuracy,
  classification report, confusion matrix) reported in `docs/`.
- **Live local demo:** see `src/vision/README.md` (separate workstream; not part of this
  Midterm submission).

## Sample Results

- **Test accuracy:** 88.15% (409/464 correct), macro F1 0.8813, weighted F1 0.8812.
- **Per-class F1:** Cardboard 0.8741, Glass 0.8750, Metal 0.8898, Paper 0.8944, Plastic 0.8731.
- **Most confused pairs:** Metal/Plastic (9 each way), Cardboard to Paper (7), Plastic to Glass
  (7).
- Full classification report, confusion matrix figure, and misclassified-example figure are in
  the notebook (Step 6) and reproduced in the report (`docs/`).

## Links to Required Project Materials

- Dataset: [RealWaste, UCI ML Repository](https://doi.org/10.24432/C5SS4G) (CC BY 4.0).
- Report, as submitted and as corrected: `docs/Midterm - Computer Vision Project Report.pdf`,
  `docs/Midterm - Computer Vision Project Report.docx`.
- Training/evaluation notebook: `src/training/Midterm_Object_Sorting_RealWaste.ipynb`.
- Model documentation: `models/README.md`. Dataset documentation: `dataset/README.md`.
- Live demo: `src/vision/README.md` (separate workstream, not yet landed).
- Planned for the Final project: `demonstration/README.md`, `results/test_1/`,
  `results/test_2/`.
