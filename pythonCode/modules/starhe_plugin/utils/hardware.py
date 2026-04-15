"""
utils/hardware.py — Hardware detection for adaptive RTMDet batch sizing
========================================================================
Detects GPU VRAM and system RAM to compute the optimal batch size
for RTMDet 640×640 inference.
"""

import os

# ── Tuning constants ──────────────────────────────────────────────────────────
# Estimated VRAM/RAM cost per frame during RTMDet 640×640 forward pass (MB).
# Covers input tensor (4.9 MB) + intermediate feature maps + head outputs.
_FRAME_COST_MB = 50

# Hard caps
_MAX_BATCH_GPU = 32
_MAX_BATCH_MPS = 16   # Apple Silicon: GPU shares RAM, be conservative
_MAX_BATCH_CPU = 4

# Fraction of free memory actually used (safety margin)
_GPU_SAFETY  = 0.80
_MPS_SAFETY  = 0.30   # unified memory: GPU + CPU share the same pool
_CPU_SAFETY  = 0.20   # conservative: only 20 % of free RAM


def get_free_ram_mb() -> float:
    """Return available system RAM in MB."""
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 ** 2)
    except ImportError:
        pass
    # Fallback for macOS / Linux without psutil (os.sysconf is Unix-only)
    try:
        pages     = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        # Total RAM × 0.5 as rough estimate of *available*
        return (pages * page_size) / (1024 ** 2) * 0.5
    except (AttributeError, ValueError, OSError):
        pass
    # Windows fallback via ctypes
    try:
        import ctypes
        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength",                ctypes.c_ulong),
                ("dwMemoryLoad",            ctypes.c_ulong),
                ("ullTotalPhys",            ctypes.c_ulonglong),
                ("ullAvailPhys",            ctypes.c_ulonglong),
                ("ullTotalPageFile",        ctypes.c_ulonglong),
                ("ullAvailPageFile",        ctypes.c_ulonglong),
                ("ullTotalVirtual",         ctypes.c_ulonglong),
                ("ullAvailVirtual",         ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullAvailPhys / (1024 ** 2)
    except Exception:
        return 4096.0  # conservative fallback: assume 4 GB free


def compute_optimal_batch_size(
    device: str = "cpu",
    vram_free_mb: float | None = None,
) -> int:
    """
    Compute the optimal RTMDet batch size from available memory.

    Parameters
    ----------
    device : str
        ``"cuda"``, ``"mps"``, or ``"cpu"``.
    vram_free_mb : float | None
        Free VRAM in MB **after model loading** (CUDA only).
        If *None* and *device* is ``"cuda"``, attempts auto-detection.

    Returns
    -------
    int
        Optimal batch size (≥ 1).
    """
    if device == "cuda":
        if vram_free_mb is None:
            try:
                import torch
                if torch.cuda.is_available():
                    vram_free_mb = torch.cuda.mem_get_info(0)[0] / (1024 ** 2)
            except Exception:
                pass

        if vram_free_mb is not None:
            usable = vram_free_mb * _GPU_SAFETY
            batch  = max(1, int(usable / _FRAME_COST_MB))
            return min(batch, _MAX_BATCH_GPU)

    if device == "mps":
        total_ram = get_free_ram_mb() * 2  # get_free_ram_mb returns ~50% of total
        usable    = total_ram * _MPS_SAFETY
        batch     = max(1, int(usable / _FRAME_COST_MB))
        return min(batch, _MAX_BATCH_MPS)

    # CPU fallback
    ram_free = get_free_ram_mb()
    usable   = ram_free * _CPU_SAFETY
    batch    = max(1, int(usable / _FRAME_COST_MB))
    return min(batch, _MAX_BATCH_CPU)
