from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from virtuoso_bridge.virtuoso import x11


def _load_helper_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "virtuoso_bridge"
        / "resources"
        / "x11_dismiss_dialog.py"
    )
    spec = importlib.util.spec_from_file_location("x11_dismiss_dialog_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _xwininfo_window(*, x=0, y=0, w=100, h=100, mapped=True):
    state = "IsViewable" if mapped else "IsUnMapped"
    return f"""
xwininfo: Window id: 0x1

  Absolute upper-left X:  {x}
  Absolute upper-left Y:  {y}
  Width: {w}
  Height: {h}
  Map State: {state}
"""


def test_discover_windows_reports_child_modal_title(monkeypatch) -> None:
    helper = _load_helper_module()

    root = """
xwininfo: Window id: 0xroot (the root window)

  Root window id: 0xroot
  Parent window id: 0x0 (none)
     2 children:
     0xc58227 (has no name): () 843x132+528+477 +528+477
     0xabc000 "Virtuoso Main": ("virtuoso" "virtuoso") 1400x900+0+0 +0+0
"""
    ade_tree = """
xwininfo: Window id: 0xc58227 (has no name)

  Root window id: 0xroot
  Parent window id: 0xroot
     1 child:
     0x4203583 "ADE Explorer Update and Run": ("virtuoso" "virtuoso") 843x132+0+0 +528+477
"""
    main_tree = """
xwininfo: Window id: 0xabc000 "Virtuoso Main"

  Root window id: 0xroot
  Parent window id: 0xroot
     1 child:
     0xabc111 "Virtuoso Schematic Editor": ("virtuoso" "virtuoso") 1400x900+0+0 +0+0
"""

    def fake_check_output(cmd, stderr=None):
        if cmd == ["xwininfo", "-root", "-children"]:
            return root.encode()
        if cmd == ["xwininfo", "-id", "0xc58227"]:
            return _xwininfo_window(x=528, y=477, w=843, h=132).encode()
        if cmd == ["xwininfo", "-id", "0xabc000"]:
            return _xwininfo_window(x=0, y=0, w=1400, h=900).encode()
        if cmd == ["xwininfo", "-id", "0xc58227", "-tree"]:
            return ade_tree.encode()
        if cmd == ["xwininfo", "-id", "0xabc000", "-tree"]:
            return main_tree.encode()
        raise AssertionError(f"unexpected command: {cmd!r}")

    monkeypatch.setattr(helper.subprocess, "check_output", fake_check_output)

    windows = helper.discover_windows(":1")
    ade = next(w for w in windows if w["dismiss_id"] == "0x4203583")
    main = next(w for w in windows if w["dismiss_id"] == "0xabc111")

    assert ade["frame_id"] == "0xc58227"
    assert ade["title"] == "ADE Explorer Update and Run"
    assert ade["kind"] == "known_modal"
    assert ade["suggested_action"] == "enter"
    assert ade["geometry"] == {"w": 843, "h": 132, "x": 528, "y": 477}
    assert main["kind"] == "main_window"
    assert main["suggested_action"] is None

    dialogs = helper.find_dialogs(":1")
    assert [d["window_id"] for d in dialogs] == ["0x4203583"]


class _Runner:
    def __init__(self, stdout_by_marker: dict[str, str]) -> None:
        self.commands: list[str] = []
        self.uploads: list[tuple[Path, str]] = []
        self.stdout_by_marker = stdout_by_marker

    def run_command(self, command: str, timeout=None):
        self.commands.append(command)
        if command.startswith("mkdir -p "):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "python3 --version" in command:
            return SimpleNamespace(returncode=0, stdout='Python 3.9\nCMD:python3\n', stderr="")
        for marker, stdout in self.stdout_by_marker.items():
            if marker in command:
                return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def upload(self, local_path: Path, remote_path: str):
        self.uploads.append((local_path, remote_path))


def test_x11_wrapper_lists_and_dismisses_explicit_window(monkeypatch) -> None:
    monkeypatch.setattr(x11, "load_vb_env", lambda: None)
    monkeypatch.setattr("virtuoso_bridge.transport.remote_paths.load_vb_env", lambda: None)
    monkeypatch.delenv("VB_REMOTE_SCRATCH_ROOT", raising=False)
    monkeypatch.setenv("VB_CLIENT_ID", "90590")
    runner = _Runner({
        "--list-windows": '{"dismiss_id":"0x4203583","title":"ADE Explorer Update and Run"}\n',
        "--dismiss-window": '{"dismissed":"0x4203583","action":"enter"}\n',
    })

    windows = x11.list_windows(runner, "designer", profile=None)
    result = x11.dismiss_window(runner, "designer", "0x4203583", action="enter")

    assert windows == [{"dismiss_id": "0x4203583", "title": "ADE Explorer Update and Run"}]
    assert result == [{"dismissed": "0x4203583", "action": "enter"}]
    assert any("--list-windows --json :".split()[0] in cmd for cmd in runner.commands)
    assert any("--dismiss-window 0x4203583 --action enter" in cmd for cmd in runner.commands)
