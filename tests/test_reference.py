from pathlib import Path
import subprocess
import sys
import pytest

def test_official_reference():
    candidates = [Path("build/rs_reference.exe"), Path("build/rs_reference")]
    executable = next((p for p in candidates if p.exists()), None)
    if executable is None:
        pytest.skip("Official C++ executable not built; comparison is NOT validated by this run")
    subprocess.run([sys.executable, "-m", "scripts.validate_reference",
                    "--executable", str(executable)], check=True, timeout=60)
