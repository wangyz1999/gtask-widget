import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GTASK_WIDGET_HOME"] = tempfile.mkdtemp(prefix="gtask-tests-")
