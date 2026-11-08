# Coreの契約メタデータを、ローカルMCPから照会する実験

公開Veripsa Coreの抽出結果を固定snapshotへ投影し、公式Python SDK 2.3.0のstdio MCPで読む例です。
Core本体の変更はありません。製品として提供中の「Veripsa MCP」ではなく、実行できる検討用コードです。

## まず動かす

GitとPython 3.12を用意します。以下はPOSIXのパス表記です。Windowsでは仮想環境のScripts内を指定します。

```sh
git clone https://github.com/RollNuts/zenn-content.git
cd zenn-content/examples/core-local-mcp
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python client_demo.py
.venv/bin/python verify.py --report wire-verification.json
```

cloneとpackage installにはネットワークを使います。実行環境はmacOS/Python 3.12.13、SDK 2.3.0です。
同梱のdemoは架空のRust/TypeScriptから作ったメタデータなので、上記の実行にCoreやRust/npm環境は不要です。
`client_demo.py`はMCPサーバーを別プロセスで起動し、ネゴシエーション、tools/list、tools/callを行って終了します。
サーバー関数を直接呼ぶだけの検査ではありません。

既定の入力は`src-tauri/commands.rs`です。`tauri_command::receipt_label`を介して`src/client.ts`が返ります。

## 公開する2ツール

| ツール | 入力 | 返すもの |
| --- | --- | --- |
| graph_summary | なし | ファイル数、解析状態、Tauri契約の件数、snapshotの識別情報 |
| tauri_related_files | 相対path、limit（1〜20） | 同じTauri契約に接続したファイルと、関係の根拠・曖昧さ |

サーバーが読むsnapshotは起動する人が`--snapshot`で1つ選びます。ツール引数から別のファイル・repo・URLを読む機能はありません。
ツールは読み込み済みメタデータを照会し、DB、GitHub API、ソース本文、書き込み・マージ機能へは接続しません。
HTTPポートも開きません。stdioのstdoutはSDKのプロトコル通信に使います。

MCPホストへ登録するときの起動コマンドは、絶対パスで次の形になります。

```text
/path/to/.venv/bin/python /path/to/server.py --snapshot /path/to/snapshot.json
```

`server.py`を単独起動するとMCP通信待ちに入ります。動作確認には上記の`client_demo.py`を使えます。
各IDE/ホストへの登録は今回自動設定しておらず、検証したクライアントは同梱の公式SDKクライアントです。

## 4つのdemo

元の架空コードは[別の再現例](../tauri-command-contract/fixtures)にあります。
ここでは`src/client.ts`を問い合わせた場合の結果を比べます。

| 入力 | 関係行 | status |
| --- | ---: | --- |
| official-literal：公式invokeと既知のリテラル名 | 1 | observed |
| local-invoke：同名の自作関数 | 0 | not_observed |
| dynamic-name：名前を変数で渡す | 0 | not_observed |
| duplicate-command：同名のRust定義2つ | 2 | uncertain |

`observed`はこの抽出器で関係が観測されたこと、`uncertain`は曖昧・不完全な証拠を含むことです。
`not_observed`は、このsnapshot・問い合わせ範囲で関係が出なかったことです。依存がない、安全に変更できる、という判定ではありません。
`alters`と`queries`もCoreの役割名であり、実際の副作用やread/writeを検査した結果ではありません。

## 自分のローカルrepoからsnapshotを作る

これは起動する人が行う操作です。MCPクライアントから指定repoを走査するツールは公開していません。
抽出器は固定した公開commitを使い、関連24ファイルのblobも照合します。

```sh
git clone https://github.com/RollNuts/veripsa.git core
git -C core checkout d22d44f12112784d34d5ea7ba20755ca995adad2
.venv/bin/python -m pip install --only-binary=:all: --no-deps -r requirements-extract.txt
.venv/bin/python export_snapshot.py --core core --repo /path/to/your/project --out local-snapshot.json
.venv/bin/python client_demo.py --snapshot local-snapshot.json --path src-tauri/commands.rs
```

Git実行ファイルを選ぶ場合、export_snapshot.pyに`--git /path/to/git`を追加できます。
この依存定義はRust/TS/JSの例に必要な範囲であり、Core全体の言語/runtime依存ではありません。
ソース本文は抽出時にローカルで読みます。保存するsnapshotはファイルパス、TauriコマンドID、辺の役割、状態、件数などの限定した投影です。
raw graphのroot、本文・signature・任意のprovenanceなどはそのまま転送しません。

Coreは[Business Source License 1.1](https://github.com/RollNuts/veripsa/blob/d22d44f12112784d34d5ea7ba20755ca995adad2/LICENSE)のsource-availableです。エンジンはこの例に同梱していません。
このrepoの原稿・例の再利用条件は[repo README](../../README.md)を参照してください。

## 検査と限界

`verify.py`は4つの合成snapshotについて実stdio通信を検査します。解析状態・不正なメタデータ・重複ID・存在しないendpoint・パスの逸脱・limit・長いUTF-8パスの出力上限も確認します。
snapshotの上限は5MiB、問い合わせ結果は最大20行、JSON本文は32KiBまでです。切り詰めた場合は`truncated`と全関係行数を返します。MCPメッセージ全体のフレームサイズを32KiBとする意味ではありません。

重要な範囲は以下です。

- Tauriのapp_command、alters/queriesだけを照会する実験です。Coreの他のresourceやSQL上の衝突判定を実装したものではありません。
- snapshotは固定です。作成後の編集、dirty tree、異なるworktreeの状態を追跡しません。常に`current_worktree_verified: false`と`current_state_or_merge_safety_proven: false`を返します。
- 登録表、型、capability、実行時のTauri動作、マージの正しさは検証しません。
- ファイル名・コマンド名も機密情報になり得ます。本文を除いても「情報がない」とは言えません。ホストが結果をLLMへ送るかどうかは、そのホストの設定と運用に依存します。
- snapshotは起動する人が選ぶデータです。返る名前は信頼された指示ではありません。結果を読むエージェントにも、repo由来のデータとして扱わせる必要があります。
- 大規模repoの性能、全MCPホストとの互換、production用途の完全な隔離は今回測定していません。Coreホスト版も停止中です。

参考：[MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)、[stdioの実行方法](https://py.sdk.modelcontextprotocol.io/run/)。
