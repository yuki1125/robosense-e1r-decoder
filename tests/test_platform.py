"""Check installed distribution markers against supported CPU environments."""
from importlib.metadata import requires

import pytest
from packaging.markers import default_environment
from packaging.requirements import Requirement


@pytest.mark.parametrize("system,machine,version", [
    ("linux", "aarch64", "3.10"), ("linux", "arm64", "3.11"),
    ("linux", "x86_64", "3.10"), ("win32", "AMD64", "3.12"),
    ("darwin", "arm64", "3.11"),
])
def test_viewer_dependencies(system, machine, version):
    env = dict(default_environment(), sys_platform=system,
               platform_machine=machine, python_version=version, extra="viewer")
    selected = [r for value in requires("e1r-decoder")
                if (r := Requirement(value)).marker is None or r.marker.evaluate(env)]
    open3d = [r for r in selected if r.name == "open3d"]
    assert len(open3d) == 1
    arm = system == "linux" and machine in ("aarch64", "arm64")
    assert ("0.18.0" in open3d[0].specifier) == arm
    assert ("0.19.0" in open3d[0].specifier) != arm
    numpy = [r for r in selected if r.name == "numpy"]
    assert all("1.26.4" in r.specifier for r in numpy)
    assert all("2.0.0" in r.specifier for r in numpy) != arm
    env["extra"] = ""
    assert not any(r.name == "open3d" and r.marker.evaluate(env)
                   for r in map(Requirement, requires("e1r-decoder")))
