# Claude Code 用のひな形

| ファイル | 置き場所 | 中身 |
|---|---|---|
| `settings.json` | プロジェクトの `.claude/settings.json` | 秘密ファイルの読み取り禁止、送信・強制 push の禁止、公開系は確認、hook とサンドボックスの有効化 |
| `hooks/guard.py` | プロジェクトの `.claude/hooks/guard.py` | 実行の直前に危ない操作を止める・確認に回す（依存なしの Python） |
| `managed-settings.json` | 組織で配る管理設定（場所は [docs/03](../../docs/03-claude-code.md#7-組織で配る設定管理設定)） | `bypassPermissions` の無効化と最低限の deny |

## 使い方

```bash
mkdir -p .claude/hooks
cp templates/claude-code/settings.json .claude/settings.json
cp templates/claude-code/hooks/guard.py .claude/hooks/guard.py
```

コピーしたあと、Claude Code で `/permissions` を開いて、意図どおりのルールが入っているかを確かめてください。

## 調整するところ

- `allow` はプロジェクトに合わせて書き換える（例は npm）。**allow は最小限に**
- `deny` の `Bash(curl *)` を入れると、Claude Code が `curl` を使えなくなる。外部 API を叩く作業がある場合は、`ask` に移すか、サンドボックスのネットワーク許可リスト（`sandbox.network.allowedDomains`）で宛先を絞る
- サンドボックスは macOS と Linux / WSL2 で動く（Linux は `bubblewrap` と `socat` が必要）。**Windows のネイティブ環境では効かない**
- `.env.example` のように中身のない見本ファイルは、hook では許している。settings の deny には入れていない

## 限界

deny ルールも hook も、**コマンドの文字列とパスで判断**します。言い換え（別のパスから同じプログラムを呼ぶ、`sh -c` の中に入れる）までは防げません。
本当の境界はサンドボックス・コンテナ・VM です。`bypassPermissions` はその中でだけ使ってください。
