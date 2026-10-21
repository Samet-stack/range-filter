"""Shared forecast contract and GPU exclusion for the terminal and local experiments."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import os

ROOT = Path(__file__).resolve().parent
KRONOS_ROOT = Path.home() / "kronos"
CONTEXT = 400
HORIZON = 12
TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
BASE_MODEL = "NeoQuasar/Kronos-small"
EXPERIMENT = ROOT / "backtest" / "experiments" / "crypto-volume-v2"
GPU_LOCK = Path("/tmp") / f"range-filter-kronos-{os.getuid()}.lock"


@contextmanager
def gpu_slot():
    """Fail fast when another process trains/forecasts; never queue obsolete GPU work."""
    with GPU_LOCK.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BlockingIOError("Kronos est occupé par un autre calcul. Réessaie dans un instant.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
