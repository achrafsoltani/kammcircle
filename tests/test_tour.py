"""The watched tour in tools/tour.py must keep working as the window changes: run it quickly and headless."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[1]


def test_the_quick_tour_passes_every_check(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / "config"))
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "tour.py"), "--quick"], env=env, cwd=tmp_path,
                          capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    assert "RESULT:" in done.stdout and "FAIL " not in done.stdout
    assert not any((tmp_path / "config").rglob("*"))  # nothing written to the user's settings folder
