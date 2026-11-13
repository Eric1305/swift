"""Array backend: CuPy on the GB10 GPU when available, NumPy otherwise. Same code either way."""
import numpy as np

try:
    import cupy as xp
    from cupyx.scipy import ndimage

    xp.zeros(1).sum()  # fail fast if the driver/runtime can't actually run
    GPU = True
except Exception:  # no CuPy, or no usable GPU
    xp = np
    from scipy import ndimage

    GPU = False


def to_numpy(array) -> np.ndarray:
    return array.get() if GPU and hasattr(array, "get") else np.asarray(array)


BACKEND = "cupy (GB10 GPU)" if GPU else "numpy (CPU)"
