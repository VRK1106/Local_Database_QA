"""Memory Management & Optimization Utilities.
Ensures aggressive garbage collection, glibc malloc trimming, and memory observability for production containers.
"""

from __future__ import annotations
import gc
import os
import sys
import ctypes

_libc = None
try:
    if sys.platform.startswith("linux"):
        _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None


def trim_memory() -> int:
    """
    Force Python garbage collection and trigger glibc malloc_trim.
    Releases freed heap memory back to the operating system kernel immediately,
    preventing persistent RSS bloat in containerized environments.
    """
    collected = gc.collect()
    trimmed = False
    if _libc is not None and hasattr(_libc, "malloc_trim"):
        try:
            trimmed = bool(_libc.malloc_trim(0))
        except Exception:
            trimmed = False
    return collected


def get_process_memory_mb() -> dict[str, float]:
    """
    Return current process resident set size (RSS) and virtual memory size (VMS) in MB.
    Uses Linux /proc filesystem when available, falling back to basic metrics.
    """
    rss_mb = 0.0
    vms_mb = 0.0

    # Linux /proc/self/status parsing (zero-overhead, no external deps)
    status_file = "/proc/self/status"
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            rss_mb = float(parts[1]) / 1024.0
                    elif line.startswith("VmSize:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            vms_mb = float(parts[1]) / 1024.0
            return {"rss_mb": round(rss_mb, 2), "vms_mb": round(vms_mb, 2)}
        except Exception:
            pass

    return {"rss_mb": round(rss_mb, 2), "vms_mb": round(vms_mb, 2)}
