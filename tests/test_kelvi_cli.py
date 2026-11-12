import tempfile
from pathlib import Path

from kelvi.cli import init_project


def test_cli_init_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "my_test_agent"
        init_project(target, template="clinic")

        assert (target / "agent.yaml").exists()
        assert (target / "tools.py").exists()
        assert (target / "main.py").exists()
        assert (target / ".env.example").exists()
        assert (target / "README.md").exists()

        content = (target / "tools.py").read_text(encoding="utf-8")
        assert "@tool" in content
        assert "check_availability" in content
