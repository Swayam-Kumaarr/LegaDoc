import subprocess
import sys

steps = [
    ("Image Preprocessing", "app/preprocess.py"),
    ("PaddleOCR", "app/ocr.py"),
    ("FIR Parser", "app/parser.py"),
    ("FIR Semantic AI", "app/semantic.py"),
    ("Retention Layer", "-m app.test_database")
]

print("\n========== FIR OCR PIPELINE ==========\n")

for name, command in steps:

    print(f"\nRunning: {name}")

    if command.startswith("-m"):
        result = subprocess.run(
            [sys.executable] + command.split(),
            check=False
        )
    else:
        result = subprocess.run(
            [sys.executable, command],
            check=False
        )

    if result.returncode != 0:
        print(f"\n{name} failed!")
        sys.exit(1)

print("\n======================================")
print("FIR OCR PIPELINE COMPLETED!")
print("======================================")