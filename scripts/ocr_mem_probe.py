"""
Peak-memory probe for the OCR worker. Answers "how much RAM does one scan
really need?" before you pick a VM size or an ocr_worker mem_limit.

Runs inside the ocr_worker image, one configuration per container, so each
number is a clean process peak. From the repo root:

  docker run --rm --memory 3500m --memory-swap 3500m \
    -e OMP_NUM_THREADS=2 -e MALLOC_ARENA_MAX=2 -e OBJECT_STORAGE_BACKEND=local \
    -v "$PWD/scripts":/probe:ro -v "$PWD/samples":/samples:ro \
    <ocr_worker image> python /probe/ocr_mem_probe.py both /samples/scan.png

Modes:
  both        what worker.py does today: preprocess, then Hindi + English passes
  both_nopre  same engines on the raw image (skips the 1.5x upscale + denoise)
  en | hi     one engine only
  tesseract   the fallback engine only

PROBE_KW='{"rec_batch_num": 1}' passes extra PaddleOCR(...) arguments, to try
a setting before changing worker.py.

Prints one JSON line. A run killed at its --memory cap prints nothing and the
container exits 137 — treat that as "needs more than the cap".

Measured on an arm64 Mac, Docker cap 2.2 GB, one 768x1024 FIR scan (Sep 2026):
  tesseract 469 MiB · hi 1,467 MiB · en OOM (>2.2 GB) · both OOM · both_nopre OOM
"""

import json
import os
import resource
import sys
import tempfile
import time

mode, path = sys.argv[1], sys.argv[2]
extra = json.loads(os.environ.get("PROBE_KW") or "{}")
sys.path.insert(0, "/worker")
sys.path.insert(0, "/api")
os.environ.setdefault("OBJECT_STORAGE_BACKEND", "local")


def peak_mib():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024  # Linux reports KiB


import worker as w  # noqa: E402  (imports paddle/cv2 exactly as the Celery worker does)

with open(path, "rb") as fh:
    data = fh.read()
out = {"mode": mode, "extra": extra, "after_imports_mib": peak_mib()}
t0 = time.time()

img = data if mode.endswith("_nopre") else w.preprocess_image_bytes(data)
out["after_preprocess_mib"] = peak_mib()

if mode == "tesseract":
    boxes = w.run_tesseract_fallback(img)
    out["after_models_mib"] = out["after_preprocess_mib"]
else:
    from paddleocr import PaddleOCR

    langs = {"en": ["en"], "hi": ["hi"], "both": ["hi", "en"], "both_nopre": ["hi", "en"]}[mode]
    kw = {"use_angle_cls": True, "show_log": False, **extra}
    engines = [PaddleOCR(lang=lang, **kw) for lang in langs]
    out["after_models_mib"] = peak_mib()
    boxes = []
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        tmp.write(img)
        tmp.flush()
        for engine in engines:
            result = engine.ocr(tmp.name, cls=kw["use_angle_cls"])
            if result and result[0]:
                boxes.extend(result[0])

out["peak_mib"] = peak_mib()
out["boxes"] = len(boxes)
out["seconds"] = round(time.time() - t0, 1)
print(json.dumps(out))
