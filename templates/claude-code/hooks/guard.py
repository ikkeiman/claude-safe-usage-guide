#!/usr/bin/env python3
"""Claude Code の PreToolUse hook。危ない操作を、実行の直前に止める・人の確認に回す。

標準入力で受け取る JSON（主な項目）:
  tool_name   道具の名前（Bash / Read / Edit / Write など）
  tool_input  道具への入力（Bash なら command、Read なら file_path）

判定は次の JSON を標準出力に書いて返す（何も書かずに終了コード 0 なら、通常の確認の流れに任せる）。
  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                          "permissionDecision": "deny" | "ask",
                          "permissionDecisionReason": "理由"}}

注意: この hook はコマンドの文字列とパスで判断する。言い換え（別名・別のパス・sh -c の中）には弱い。
「うっかり」を止める網であって、悪意のある回避を防ぐ境界ではない。境界はサンドボックスやコンテナで作る。
依存なし（Python 3.9 以上の標準ライブラリだけ）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePath

# ---- 秘密ファイル --------------------------------------------------------------

SECRET_NAME_PATTERNS = [
    re.compile(r"^\.env$"),
    re.compile(r"^\.env\.(?!example$|sample$|template$).+"),  # .env.local など。.env.example は許す
    re.compile(r".+\.(pem|key|p12|pfx|ppk|jks|keystore)$", re.IGNORECASE),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)$"),
    re.compile(r"^credentials.*\.json$", re.IGNORECASE),
    re.compile(r"^service[-_]?account.*\.json$", re.IGNORECASE),
    re.compile(r"^\.netrc$"),
    re.compile(r"^\.npmrc$"),
]
SECRET_DIR_PARTS = [(".ssh",), (".aws", "credentials"), (".gnupg",), (".config", "gcloud")]


def is_secret_path(path: str) -> bool:
    p = PurePath(path.replace("\\", "/"))
    if any(pat.match(p.name) for pat in SECRET_NAME_PATTERNS):
        return True
    parts = p.parts
    for seq in SECRET_DIR_PARTS:
        n = len(seq)
        for i in range(len(parts) - n + 1):
            if tuple(parts[i : i + n]) == seq:
                return True
    return False


# ---- コマンド -------------------------------------------------------------------

DENY_COMMAND_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z|da)?sh\b"),
        "取ってきたスクリプトをそのまま実行しようとしています（curl | sh）。中身を確かめてから実行してください",
    ),
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)[a-zA-Z]*\s+(/|~|\$HOME|\*|\.)(\s|/?$|/\*)"),
        "広い範囲を削除しようとしています（rm -rf / ~ * .）",
    ),
    (
        re.compile(r"\bgit\s+push\b.*\s(--force(?!-with-lease)|-f)(\s|$)"),
        "履歴を強制的に書き換えようとしています（git push --force）。人が判断してください",
    ),
    (
        re.compile(r"\b(printenv|env)\s*(\||$|>)"),
        "環境変数をまとめて出力しようとしています。秘密が含まれることがあります",
    ),
]

ASK_COMMAND_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgit\s+push\b"), "リモートに送ります（git push）"),
    (re.compile(r"\b(npm|pnpm|yarn)\s+publish\b"), "パッケージを公開します"),
    (re.compile(r"\b(twine|uv)\s+(upload|publish)\b"), "パッケージを公開します"),
    (
        re.compile(r"\bcurl\b.*\s(-X\s*(POST|PUT|PATCH|DELETE)|--data\b|-d\s|-F\s|--form\b)"),
        "外部にデータを送ります（curl）",
    ),
    (
        re.compile(r"\bgh\s+(pr\s+merge|release\s+create|repo\s+(delete|edit))\b"),
        "GitHub 上で取り消しにくい操作をします",
    ),
]

TOKEN_RE = re.compile(r"""[^\s'"|;&<>()]+""")


def secret_paths_in_command(command: str) -> list[str]:
    """コマンドの中に出てくる秘密ファイルらしいパスを返す。"""
    found = []
    for tok in TOKEN_RE.findall(command):
        tok = tok.strip("'\"")
        if tok.startswith("-") or "=" in tok and not tok.startswith((".", "/", "~")):
            continue
        if is_secret_path(tok):
            found.append(tok)
    return found


# ---- 判定 ------------------------------------------------------------------------


def decide(payload: dict) -> tuple[str, str] | None:
    """(判定, 理由) を返す。判定は "deny" か "ask"。何もしないなら None。"""
    tool = payload.get("tool_name", "")
    data = payload.get("tool_input") or {}

    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = str(data.get("file_path") or data.get("notebook_path") or data.get("path") or "")
        if path and is_secret_path(path):
            return "deny", f"秘密情報のファイル（{PurePath(path).name}）には触れない設定です"
        return None

    if tool == "Bash":
        command = str(data.get("command") or "")
        for pat, reason in DENY_COMMAND_RULES:
            if pat.search(command):
                return "deny", reason
        secrets = secret_paths_in_command(command)
        if secrets:
            return "deny", f"秘密情報のファイル（{PurePath(secrets[0]).name}）をコマンドで扱おうとしています"
        for pat, reason in ASK_COMMAND_RULES:
            if pat.search(command):
                return "ask", reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # 入力が読めないときは止めない（通常の確認の流れに任せる）
        return 0
    result = decide(payload)
    if result is None:
        return 0
    decision, reason = result
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": f"[guard] {reason}",
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
