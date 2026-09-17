"""Logging: rotating file under LOG_DIR plus stderr (launchd captures stderr too)."""
from __future__ import annotations

import logging
import logging.handlers

from .config import LOG_DIR, ensure_dirs


def setup(verbose: bool = False) -> None:
    ensure_dirs()
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "server.log", maxBytes=5_000_000, backupCount=5)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.handlers[:] = [fh, sh]
