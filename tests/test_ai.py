import json
import subprocess

import pytest

from pegasus.config import get_settings
from pegasus.intel import ai


@pytest.fixture
def cli_backend(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-test")
    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/local/bin/claude")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_backend_selection(monkeypatch):
    get_settings.cache_clear()
    assert get_settings().ai_backend is None and not get_settings().ai_enabled
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-test")
    get_settings.cache_clear()
    assert get_settings().ai_backend == "cli"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-test")
    get_settings.cache_clear()
    assert get_settings().ai_backend == "api"
    get_settings.cache_clear()


def test_label_tags_through_claude_cli(cli_backend, monkeypatch):
    calls = []

    def fake_run(cmd, input, env, **kw):
        calls.append((cmd, input, env))
        out = {"type": "result", "subtype": "success", "is_error": False,
               "result": '{"tags":["deck"],"confidence":0.97}',
               "structured_output": {"tags": ["deck"], "confidence": 0.97}}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr="")

    monkeypatch.setattr(ai.subprocess, "run", fake_run)
    assert ai.label_tags("Construct composite deck", ["deck", "roof"]) == (["deck"], 0.85)
    cmd, prompt, env = calls[0]
    assert cmd[:2] == ["/usr/local/bin/claude", "-p"] and "--json-schema" in cmd
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    assert "Construct composite deck" in prompt
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat-test" and "ANTHROPIC_API_KEY" not in env


def test_claude_cli_failure_returns_none(cli_backend, monkeypatch):
    monkeypatch.setattr(ai.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, stdout=json.dumps({"subtype": "error_max_turns", "is_error": True}), stderr=""))
    assert ai.ask_json("sys", "user", {"type": "object"}) is None
    monkeypatch.setattr(ai.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, stdout="", stderr="Invalid API key"))
    assert ai.ask_json("sys", "user", {"type": "object"}) is None
