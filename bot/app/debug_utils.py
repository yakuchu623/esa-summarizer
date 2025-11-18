import time
import logging
from contextlib import contextmanager

logger = logging.getLogger("debug_utils")


@contextmanager
def step(name: str):
    start = time.time()
    logger.debug(f"[STEP start] {name}")
    try:
        yield
    finally:
        elapsed = (time.time() - start) * 1000
        logger.debug(f"[STEP end] {name} elapsed={elapsed:.2f}ms")


def log_kv(prefix: str, **kwargs):
    parts = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
    logger.debug(f"{prefix} {parts}")


def truncate(text: str, limit: int = 200):
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + "..."
