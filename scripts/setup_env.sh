#!/usr/bin/env bash
# One-command dev environment setup: creates .venv, installs pinned requirements,
# registers a Jupyter kernel for the notebook, and checks TensorFlow GPU visibility.
#
# Usage: ./scripts/setup_env.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_VERSION=$(cat .python-version 2>/dev/null || echo "3.12")
echo "Using python: $(command -v python3) ($(python3 --version))"
echo "Pinned .python-version: $PYTHON_VERSION"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  echo "Created .venv"
else
  echo ".venv already exists, reusing it"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

python -m ipykernel install --user --name cv-object-sorting --display-name "cv-object-sorting (.venv)"
echo "Registered Jupyter kernel: cv-object-sorting"

echo ""
echo "=== TensorFlow / GPU check ==="
python - <<'PYEOF'
import tensorflow as tf
print("TensorFlow", tf.__version__)
gpus = tf.config.list_physical_devices("GPU")
if gpus:
    print("GPU visible:", gpus)
else:
    print("No GPU visible to TensorFlow - training runs on CPU (the default; MobileNetV2")
    print("on ~3k images finishes in well under an hour). For GPU acceleration instead,")
    print("install 'tensorflow[and-cuda]==2.21.0' in place of the plain 'tensorflow' pin.")
PYEOF

echo ""
echo "Setup complete. Activate with: source .venv/bin/activate"
