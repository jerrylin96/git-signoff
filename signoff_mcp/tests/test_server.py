"""MCP layer smoke tests (skipped when the optional `mcp` SDK is absent)."""

import asyncio

import pytest

mcp = pytest.importorskip("mcp")

from signoff_mcp.server import create_server  # noqa: E402


@pytest.fixture
def server(scratch_repo):
    return create_server(str(scratch_repo))


def test_tools_registered(server):
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"signoff_prepare", "signoff_commit", "signoff_push_notes"}


def test_prepare_then_commit_flow(server, tmp_path, monkeypatch):
    transcript = tmp_path / "t.log"
    transcript.write_bytes(b"session bytes\n")
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(transcript))

    prep = asyncio.run(server.call_tool("signoff_prepare", {"reference_ref": "main"}))
    prep_data = prep[1] if isinstance(prep, tuple) else prep
    assert str(prep_data).count("reviewed_commit_sha")

    result = asyncio.run(
        server.call_tool(
            "signoff_commit",
            {"tradeoffs": ["t1"], "risks": [], "user_email": "dev@example.com", "agent": "pytest"},
        )
    )
    assert "VERIFIED_BY_HUMAN" in str(result)


def test_commit_without_prepare_reports_explicit_error(server):
    with pytest.raises(Exception, match="signoff_prepare first"):
        asyncio.run(
            server.call_tool(
                "signoff_commit",
                {"tradeoffs": [], "risks": [], "user_email": "dev@example.com"},
            )
        )


def test_server_init_subcommand(monkeypatch):
    import sys
    from unittest.mock import patch
    from signoff_mcp import server as server_mod

    monkeypatch.setattr(sys, "argv", ["signoff-mcp", "init", "--help"])
    with patch("signoff_mcp.init.main", return_value=0) as mock_init:
        with pytest.raises(SystemExit) as exc:
            server_mod.main()
        assert exc.value.code == 0
        mock_init.assert_called_once()


def test_server_help_flag(monkeypatch, capsys):
    import sys
    from signoff_mcp import server as server_mod

    monkeypatch.setattr(sys, "argv", ["signoff-mcp", "--help"])
    with pytest.raises(SystemExit) as exc:
        server_mod.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage: signoff-mcp" in captured.out
    assert "init" in captured.out




def test_git_signoff_bare_prints_help_and_never_starts_server(monkeypatch, capsys):
    """`git signoff` dispatches to the git-signoff executable; bare invocation must not
    block on stdin waiting for an MCP client."""
    import sys
    from unittest.mock import patch
    from signoff_mcp import server as server_mod

    monkeypatch.setattr(sys, "argv", ["git-signoff"])
    with patch.object(server_mod, "create_server") as mock_create:
        with pytest.raises(SystemExit) as exc:
            server_mod.cli_main()
    assert exc.value.code == 0
    mock_create.assert_not_called()
    out = capsys.readouterr().out
    assert "usage: git-signoff" in out and "serve" in out and "init" in out


def test_git_signoff_serve_runs_server(monkeypatch):
    import sys
    from unittest.mock import MagicMock, patch
    from signoff_mcp import server as server_mod

    monkeypatch.setattr(sys, "argv", ["git-signoff", "serve"])
    fake = MagicMock()
    with patch.object(server_mod, "create_server", return_value=fake):
        server_mod.cli_main()
    fake.run.assert_called_once_with("stdio")


def test_git_signoff_init_dispatches_to_initializer(monkeypatch):
    import sys
    from unittest.mock import patch
    from signoff_mcp import server as server_mod

    monkeypatch.setattr(sys, "argv", ["git-signoff", "init", "--help"])
    with patch("signoff_mcp.init.main", return_value=0) as mock_init:
        with pytest.raises(SystemExit) as exc:
            server_mod.cli_main()
    assert exc.value.code == 0
    mock_init.assert_called_once()


def test_git_signoff_unknown_command_exits_2(monkeypatch, capsys):
    import sys
    from signoff_mcp import server as server_mod

    monkeypatch.setattr(sys, "argv", ["git-signoff", "frobnicate"])
    with pytest.raises(SystemExit) as exc:
        server_mod.cli_main()
    assert exc.value.code == 2
    assert "unknown command" in capsys.readouterr().err


def test_signoff_mcp_alias_bare_still_runs_server(monkeypatch):
    import sys
    from unittest.mock import MagicMock, patch
    from signoff_mcp import server as server_mod

    monkeypatch.setattr(sys, "argv", ["signoff-mcp"])
    fake = MagicMock()
    with patch.object(server_mod, "create_server", return_value=fake):
        server_mod.main()
    fake.run.assert_called_once_with("stdio")


def test_console_scripts_declared():
    from pathlib import Path

    # No tomllib: the suite also runs on Python 3.10.
    text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    assert 'git-signoff = "signoff_mcp.server:cli_main"' in text
    assert 'signoff-mcp = "signoff_mcp.server:main"' in text
