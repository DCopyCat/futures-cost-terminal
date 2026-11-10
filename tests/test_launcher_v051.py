"""Regression: Windows launcher delegates browser opening to Streamlit only."""
from pathlib import Path


def test_windows_launcher_opens_one_browser_tab():
    launcher = (Path(__file__).resolve().parents[1] / "启动工作台.bat").read_text(encoding="utf-8")
    active_lines = [line.strip() for line in launcher.splitlines()
                    if line.strip() and not line.lstrip().lower().startswith(("rem ", "::"))]
    commands = "\n".join(active_lines).lower()
    assert "start-process" not in commands
    assert 'start "" powershell' not in commands
    assert commands.count(" -m streamlit run app.py") == 1
    assert "--server.headless false" in commands
    assert "--server.address 127.0.0.1" in commands
    assert "--server.port 8501" in commands
