# syntax=docker/dockerfile:1.7
# ============================================================================
# STARHE — deterministic processing + inference image
# ============================================================================
# Build context is the REPOSITORY ROOT:
#     docker build -f docker/Dockerfile -t starhe-pipeline:1.0 .
#
# Model weights (.pth) are deliberately NOT baked into the image: mount them
# at run time with  -v /path/to/weights:/weights  and pass --weights /weights.
#
# Reproducibility contract
#   * single platform: linux/amd64 (one arithmetic, one set of binaries)
#   * every binary pinned inside the image (ffmpeg, OpenCV, BLAS, torch)
#   * intermediate video encoded H.264 CRF 0 → mathematically lossless
#   * inference on CPU, float64, single thread
# ----------------------------------------------------------------------------

# Pin the base by digest for a fully immutable build. Replace the digest with
# the one you resolve once (docker buildx imagetools inspect python:3.13-slim).
FROM --platform=linux/amd64 python:3.13-slim

LABEL org.opencontainers.image.title="STARHE deterministic pipeline" \
      org.opencontainers.image.description="DICOM → prepUS → STARHE-RISK/DETECT, byte-identical on any host" \
      org.opencontainers.image.licenses="proprietary"

# ── Determinism & runtime environment ───────────────────────────────────────
# One thread everywhere: floating-point accumulation order becomes fixed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    # STARHE flags (config.py reads these; see README "Environment overrides")
    STARHE_DETERMINISTIC=1 \
    STARHE_USE_WEASIS=0 \
    C3D_BACKEND=pytorch \
    STARHE_WEIGHTS_DIR=/weights

# ── System packages ─────────────────────────────────────────────────────────
# ffmpeg           : intermediate H.264 CRF 0 encoding + decoding
# libglib / libgl1 : shared objects required by the opencv-python wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies (own layer → cached across code changes) ────────────
# torch/torchvision come from the CPU-only index so no CUDA wheels are pulled.
# pip itself is NOT upgraded on purpose: the base image already pins it, so the
# resolver behaviour stays fixed for a given base digest.
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
         --index-url https://download.pytorch.org/whl/cpu \
         torch==2.11.0 torchvision==0.26.0 \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# ── Vendored prepUS (installed without deps: they are pinned above) ─────────
COPY third_party/prepUS /app/third_party/prepUS
RUN pip install --no-cache-dir --no-deps /app/third_party/prepUS

# ── Pin guard ───────────────────────────────────────────────────────────────
# A transitive, unpinned requirement can silently install a *newer* build on top
# of a pinned one (mmcv-lite/mmengine/sonocrop all do this with opencv-python).
# Assert the versions that actually get imported, so drift fails the build here
# instead of surfacing as a changed hash months later.
RUN python -c "\
import cv2, numpy, scipy, torch, torchvision, prepUS; \
exp = {'cv2': ('4.13.0', cv2.__version__), 'numpy': ('2.4.4', numpy.__version__), \
       'scipy': ('1.17.1', scipy.__version__), 'torch': ('2.11.0', torch.__version__), \
       'torchvision': ('0.26.0', torchvision.__version__)}; \
bad = [n + ': expected ' + e + '*, got ' + g for n, (e, g) in exp.items() if not g.startswith(e)]; \
assert not bad, 'PIN DRIFT: ' + '; '.join(bad); \
print('pin guard OK', {n: g for n, (_, g) in exp.items()})"

# ── Application code (last: changes here don't invalidate the deps layer) ───
COPY pythonCode/modules/starhe_plugin /app/pythonCode/modules/starhe_plugin
COPY scripts/starhe_pipeline_cli.py    /app/scripts/starhe_pipeline_cli.py
# Reproducibility tooling ships with the image so CI needs no bind mount.
COPY scripts/check_golden_hash.py      /app/scripts/check_golden_hash.py
COPY scripts/test_encoding_roundtrip.py /app/scripts/test_encoding_roundtrip.py
COPY scripts/diag_stage_hashes.py      /app/scripts/diag_stage_hashes.py

# Remove any weights accidentally present in the build context: the image must
# stay weight-free (they are mounted at run time).
RUN find /app/pythonCode/modules/starhe_plugin/models -name "*.pth" -delete || true

ENV PYTHONPATH=/app/pythonCode/modules

# Non-root runtime user
RUN useradd --create-home --uid 1000 starhe \
    && mkdir -p /data/in /data/out /weights \
    && chown -R starhe:starhe /app /data /weights
USER starhe

VOLUME ["/data/in", "/data/out", "/weights"]

ENTRYPOINT ["python", "/app/scripts/starhe_pipeline_cli.py"]
CMD ["--help"]
