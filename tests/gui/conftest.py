from __future__ import annotations

import os


# Keep GUI tests runnable on CI and on a workstation without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
