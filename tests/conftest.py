"""Make the package importable straight from the source tree.

Tests must run with nothing installed and no network, so ``src`` is added to
``sys.path`` here rather than relying on ``pip install -e .``.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
for path in (SRC, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)
