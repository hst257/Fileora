from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fileora.service import InstanceLock

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell runtime guards")
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.mark.parametrize("script", ["setup.ps1", "start.ps1"])
def test_scripts_reject_live_catalog_before_changing_environment(tmp_path, script):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in (script, "runtime.ps1"):
        shutil.copyfile(SCRIPTS / name, scripts / name)
    executable = tmp_path / ".venv" / "Scripts" / "fileora.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test executable")
    runtime = tmp_path / ".fileora"
    runtime.mkdir()
    lock = InstanceLock(runtime / "instance.lock")
    lock.acquire()
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(scripts / script),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode != 0
        assert "catalog is already in use" in result.stderr
        assert "Ctrl+C" in result.stderr
        assert executable.read_bytes() == b"test executable"
    finally:
        lock.release()

    # An unlocked leftover lock file must not prevent a later startup/setup.
    probe = scripts / "probe.ps1"
    probe.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        ". (Join-Path $PSScriptRoot 'runtime.ps1')\n"
        "Assert-FileoraStopped -Repo (Split-Path $PSScriptRoot -Parent)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_guard_rejects_locked_console_executable(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(SCRIPTS / "runtime.ps1", scripts / "runtime.ps1")
    executable = tmp_path / ".venv" / "Scripts" / "fileora.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test executable")
    probe = scripts / "probe.ps1"
    probe.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        ". (Join-Path $PSScriptRoot 'runtime.ps1')\n"
        "$repo = Split-Path $PSScriptRoot -Parent\n"
        "$handle = [System.IO.File]::Open((Join-Path $repo '.venv\\Scripts\\fileora.exe'),"
        " [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)\n"
        "try { Assert-FileoraStopped -Repo $repo }\n"
        "catch { Write-Error $_; exit 1 }\n"
        "finally { $handle.Dispose() }\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "already running from this environment" in result.stderr
