from __future__ import annotations

import os
from pathlib import Path

import pytest

from virtuoso_bridge.transport.ssh import CommandResult, SSHRunner
from virtuoso_bridge.transport.tunnel import SSHClient


def test_control_path_is_bounded_for_long_remote_identity(monkeypatch) -> None:
    monkeypatch.setattr("virtuoso_bridge.transport.ssh.load_vb_env", lambda: None)
    monkeypatch.setattr("virtuoso_bridge.transport.ssh._setup_command_log", lambda: None)
    monkeypatch.delenv("VB_DISABLE_CONTROL_MASTER", raising=False)
    monkeypatch.delenv("VB_FORCE_CONTROL_MASTER", raising=False)

    runner = SSHRunner(
        host="srv-elamien.ece.mcmaster.ca",
        user="noorizad",
    )

    control_path = runner._control_path
    assert Path(control_path).name.startswith("vb_ssh_")
    assert "srv-elamien" not in control_path
    assert "noorizad" not in control_path
    if os.name != "nt":
        assert len(control_path) + 18 < 104


def test_macos_unix_listener_path_too_long_is_controlmaster_failure() -> None:
    stderr = (
        'unix_listener: path "/var/folders/x/y/T/'
        'vb_ssh_noorizad@srv-elamien.ece.mcmaster.ca_direct.2BclHvp4raDoiKZF" '
        "too long for Unix domain socket"
    )

    assert SSHRunner._is_cm_failure(255, stderr)
    assert not SSHRunner._is_cm_failure(0, stderr)


def test_remote_python_detection_error_includes_ssh_stderr() -> None:
    class _FakeRunner:
        def run_command(self, command: str, timeout=None) -> CommandResult:
            return CommandResult(
                returncode=255,
                stdout="",
                stderr='unix_listener: path "/var/folders/.../vb_ssh" too long for Unix domain socket',
            )

    client = SSHClient(remote_host="localhost")
    client._ssh_runner = _FakeRunner()

    with pytest.raises(RuntimeError) as excinfo:
        client._detect_remote_python()

    msg = str(excinfo.value)
    assert "No Python interpreter found on localhost" in msg
    assert "unix_listener" in msg
    assert "SSH return code: 255" in msg
