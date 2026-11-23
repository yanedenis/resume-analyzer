"""Build the Lambda dependency layer into build/layer/python (git-ignored).

Run from anywhere:  python scripts/build_layer.py
Packages are downloaded for Lambda's platform (Linux x86_64, Python 3.11),
so it works the same from Windows, macOS or Linux.
"""
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
layer = root / "build" / "layer"
target = layer / "python"

shutil.rmtree(layer, ignore_errors=True)
target.mkdir(parents=True)

subprocess.check_call([
    sys.executable, "-m", "pip", "install",
    "-r", str(root / "requirements.txt"),
    "--target", str(target),
    "--platform", "manylinux2014_x86_64",
    "--only-binary=:all:",
    "--python-version", "3.11",
    "--implementation", "cp",
    "--upgrade",
])

for cache in target.rglob("__pycache__"):
    shutil.rmtree(cache, ignore_errors=True)

print(f"Layer built at {layer}")