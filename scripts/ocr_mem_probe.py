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
  pipeline    what worker.py does today end to end, via run_ocr_on_document_bytes:
              preprocess, Hindi + English passes, and — on a bilingual page —
              the Tesseract Devanagari pass fused in (#91). This is the mode to
              size a mem_limit from; the ones below measure single stages.
  both        preprocess, then Hindi + English passes (no Devanagari fusion)
  both_nopre  same engines on the raw image (skips the 1.5x upscale + denoise)
  en | hi     one engine only
  tesseract   the fallback engine only

PROBE_KW='{"rec_batch_num": 1}' passes extra PaddleOCR(...) arguments, to try
a setting before changing worker.py.

Prints one JSON line. A run killed at its --memory cap prints nothing and the
container exits 137 — treat that as "needs more than the cap".

Measured on an arm64 Mac, Docker cap 2.2 GB, one 768x1024 FIR scan (Sep 2026):
  tesseract 469 MiB · hi 1,467 MiB · en OOM (>2.2 GB) · both OOM · both_nopre OOM

Measured on x86_64, Docker cap 6.5 GB, cpu_threads=2, rec_batch_num=1, on the
two committed fixtures (Sep 2026), which is what the mem_limits are set from:

  haryana_fir.jpg  ~150 regions   pipeline 2,717 · both_nopre 2,572 · hi 2,274
  delhi_fir.webp   ~470 regions   pipeline 4,911 · both 5,010 · en 4,560

Peak tracks the number of text regions on the page, not its file size or the
preprocessing upscale. Confirmed not configurable away: det_limit_side_len
960/736, skipping the 1.5x upscale, FLAGS_allocator_strategy=auto_growth and
FLAGS_fraction_of_cpu_memory_to_use=0.1 each moved it by under 5%. Note the
peak also drifts up as the cap does (4,793 at 5 GB, 4,911 at 6.5 GB), so read
it as "needs roughly this much", not as a hard floor.

After #129 (wide line crops recognised in pieces, Paddle's Hindi model
dropped) and the 1920px preprocessing target, measured on x86_64 under the
cap itself:

  haryana_fir.jpg  1,651 MiB   5 s
  delhi_fir.webp   2,393 MiB  12 s   completes at a 3,000 MB cap

The same 1920px target on the old recogniser reached 5,800 MiB, because
memory tracked the width of the widest line crop. #129's arm64 figures (953 /
989 MiB) do not carry over to x86: the Delhi page is killed at a 2,000 MB cap.

What actually sets that peak is the widest line crops, not the region count:
the recognizer's memory grows with a crop's width and is not returned, and
dense forms are full of full-width lines. worker.py now recognizes any crop
wider than OCR_MAX_REC_RATIO (14) x its height in pieces cut at word gaps,
and no longer loads PaddleOCR's Hindi model at all: Tesseract `hin` runs
first, its Hindi words are masked out of the English pass, and its reading
is fused back in (#107). Same arm64 Mac, same 2.2 GB cap, pipeline mode:
  haryana_fir.jpg   main 1,599 MiB / 38 s  ->  953 MiB / 14.5 s
  delhi_fir.webp    main OOM               ->  989 MiB / 39 s
Re-measure on x86_64 before lowering the mem_limits above.
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

if mode == "pipeline":
    # The real entry point, so the number covers every engine the page
    # actually triggers — including the Tesseract Devanagari pass that a
    # bilingual FIR adds on top of both Paddle models.
    result = w.run_ocr_on_document_bytes(data, "mem-probe")
    out["after_models_mib"] = peak_mib()
    out["engine_used"] = result["engine_used"]
    out["template"] = result["template"]
    boxes = result["reconstructed_text"].split()
elif mode == "tesseract":
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
