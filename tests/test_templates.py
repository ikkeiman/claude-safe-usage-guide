"""ひな形の JSON が正しく読めて、公式ドキュメントで確認した書式に沿っているかを確かめる。"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "templates" / "claude-code"
RULE = re.compile(r"^(Bash|Read|Edit|Write|WebFetch|mcp__[A-Za-z0-9_-]+)(\(.+\))?$")
MODES = {"default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"}


def load(name):
    return json.loads((CC / name).read_text(encoding="utf-8"))


def test_project_settings_shape():
    s = load("settings.json")
    perm = s["permissions"]
    assert perm["defaultMode"] in MODES
    # プロジェクト設定では auto / bypassPermissions は効かないので書かない
    assert perm["defaultMode"] not in {"auto", "bypassPermissions"}
    for key in ("allow", "ask", "deny"):
        for rule in perm[key]:
            assert RULE.match(rule), rule
    # deny と allow が同じルールを持たない
    assert not set(perm["deny"]) & set(perm["allow"])
    assert s["sandbox"]["enabled"] is True


def test_secret_reads_are_denied():
    deny = load("settings.json")["permissions"]["deny"]
    assert "Read(.env)" in deny
    assert any(r.startswith("Read(~/.ssh") for r in deny)


def test_hooks_point_to_guard_for_each_tool():
    hooks = load("settings.json")["hooks"]["PreToolUse"]
    matchers = {h["matcher"] for h in hooks}
    assert {"Bash", "Read", "Edit", "Write"} <= matchers
    for h in hooks:
        for cmd in h["hooks"]:
            assert cmd["type"] == "command"
            assert "guard.py" in cmd["command"]


def test_managed_settings_disable_bypass():
    m = load("managed-settings.json")
    assert m["permissions"]["disableBypassPermissionsMode"] == "disable"
    for rule in m["permissions"]["deny"]:
        assert RULE.match(rule), rule
