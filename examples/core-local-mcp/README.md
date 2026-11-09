# Coreの契約メタデータを、ローカルMCPから照会する実験

公開Veripsa Coreの抽出結果を固定snapshotへ投影し、公式Python SDK 2.3.0のstdio MCPで読む例です。
実repoの抽出には、同じmoduleでimportしたTauri属性にも対応するCoreの固定commitを使用します。製品として提供中の「Veripsa MCP」ではなく、実行できる検討用コードです。

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
永続的なIDE/ホスト登録は今回自動設定していません。公式SDKクライアントに加え、下記の任意手順でCodex CLI 0.167.0からの実ツール呼び出しも確認しています。

## 4つのdemo

この4つの合成snapshotはCore `d22d44f12112784d34d5ea7ba20755ca995adad2`で作成した固定データです。上記のSDKデモと既定のCodex CLIデモは、このデータを使います。下記では更新後の固定Coreで公式Tauri例を再抽出し、SDKとCodexの両方から照会します。

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

## 初期化方式を変えて確認する

```sh
.venv/bin/python client_demo.py --legacy
```

公式Python SDK 2.3.0の`mode="legacy"`を指定する別のstdio接続です。`initialize`による交渉版は2025-11-25で、2ツールを呼べました。通常のauto接続では2026-07-28を確認しています。SDK 1.x全般や、すべての旧ホストとの互換を示す結果ではありません。モデルAPIは呼びません。

## Codex CLIから呼ぶ（任意）

この手順はCodexへログイン済みのアカウントが前提で、モデル利用枠を使います。上のSDKだけの再現と境界テストは、モデルを呼ばずに実行できます。

検証したCLIは0.167.0です。既存のCLIを置き換えず、例のディレクトリへ固定版を用意する場合は、Node.js/npmのある環境で次を実行します。

```sh
npm install --prefix .codex-cli --no-audit --no-fund --ignore-scripts @openai/codex@0.167.0
.venv/bin/python codex_demo.py --codex .codex-cli/node_modules/.bin/codex --report codex-verification-local.json
```

このCodex手順はmacOSで検証しています。Windowsでの実行は未確認です。

`codex_demo.py`は一時workspace、`--ignore-user-config`、`--ephemeral`、read-only sandbox、一回限りのMCP設定で起動します。`codex mcp add`やconfigファイルへの書き込みは行いません。`required=true`を指定し、サーバーを起動できない場合は継続しません。

`--snapshot /path/to/snapshot.json --path src-tauri/src/cmd.rs`で、起動する人が別のsnapshotと照会pathを指定できます。指定しなければ同梱の小さい合成例を使います。`related_files`は返却された関係に現れるpathを、出現順で重複除去した一覧です。

モデルへ2ツールの呼び出しを指示し、Codexの`mcp_tool_call`イベントを検査します。ツールの成功・引数・返却値・最終回答が固定snapshotと一致した場合だけ、限定した確認記録を返します。最終回答の自己申告だけで成功とは数えません。想定外のtool itemも拒否しますが、この事後検証をツール実行の強制隔離とは説明しません。

既定の合成snapshotで確認できた回答は次のとおりです。

```json
{"query_status":"observed","related_files":["src/client.ts"],"current_state_or_merge_safety_proven":false}
```

生のCodexログ、アカウント情報、環境変数は公開用の記録へ含めません。検証済みの例は`codex-verification.json`、モデルを呼ばない記録境界のテストは次のコマンドです。

```sh
.venv/bin/python -m unittest -v test_codex_receipt.py
```

参考：[OpenAI公式MCP設定](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[非対話モード](https://learn.chatgpt.com/docs/non-interactive-mode)。CLIはモデルへ結果を渡すため、本文を省いたメタデータでも送信範囲の判断は必要です。

## 自分のローカルrepoからsnapshotを作る

これは起動する人が行う操作です。MCPクライアントから指定repoを走査するツールは公開していません。
抽出器は固定した公開commitを使い、関連24ファイルのblobも照合します。

```sh
git clone https://github.com/RollNuts/veripsa.git core
git -C core checkout 9b5429aac861164cc1b41278dcaf540fa6fabad7
.venv/bin/python -m pip install --only-binary=:all: --no-deps -r requirements-extract.txt
.venv/bin/python export_snapshot.py --core core --repo /path/to/your/project --out local-snapshot.json
.venv/bin/python client_demo.py --snapshot local-snapshot.json --path src-tauri/commands.rs
```

Git実行ファイルを選ぶ場合、export_snapshot.pyに`--git /path/to/git`を追加できます。
この依存定義はRust/TS/JSの例に必要な範囲であり、Core全体の言語/runtime依存ではありません。
ソース本文は抽出時にローカルで読みます。保存するsnapshotはファイルパス、TauriコマンドID、辺の役割、状態、件数などの限定した投影です。
raw graphのroot、本文・signature・任意のprovenanceなどはそのまま転送しません。

Coreは[Business Source License 1.1](https://github.com/RollNuts/veripsa/blob/9b5429aac861164cc1b41278dcaf540fa6fabad7/LICENSE)のsource-availableです。エンジンはこの例に同梱していません。
このrepoの原稿・例の再利用条件は[repo README](../../README.md)を参照してください。

## 公式Tauri例で、import対応と解析状態を確認する

[公式Tauriの固定commit](https://github.com/tauri-apps/tauri/tree/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api)の`examples/api`を、更新後の固定Coreと同じ抽出依存で解析する手順です。アプリのbuildや起動は行いません。

```sh
git clone --depth 1 --filter=blob:none --sparse --no-checkout --branch dev https://github.com/tauri-apps/tauri.git tauri-source
git -C tauri-source sparse-checkout set examples/api
git -C tauri-source fetch --depth 1 origin 2e23492ab9bcec06bab041e0e47447aaa0da298c
git -C tauri-source checkout --detach 2e23492ab9bcec06bab041e0e47447aaa0da298c
.venv/bin/python export_snapshot.py --core core --repo tauri-source/examples/api --out tauri-api-snapshot.json
.venv/bin/python client_demo.py --snapshot tauri-api-snapshot.json --path src-tauri/src/cmd.rs
```

この手順は前節のCore checkoutと抽出依存の導入後に実行します。`--git`の指定が必要ならexporterに追加してください。

対象のRustファイルには[importした`#[command]`による`perform_request`の定義](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/src/cmd.rs#L44)があり、[Svelte内TypeScriptのliteral invoke](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src/views/Communication.svelte#L28)と[handler登録](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/src/lib.rs#L158)もソースから読めます。

旧固定Core `d22d44f`では、このファイルへの問い合わせは`not_observed`、関係行数0でした。更新後のCoreは、Rustの構文木を使い、同じmoduleが直接importした`tauri::command`、alias、入れ子のuse groupを解決します。無条件にbare `#[command]`を受理する変更ではなく、親・子・兄弟moduleへimportを流用しません。glob、reexport、macro展開、cfg評価の解決は行いません。

公開Core `9b5429a`から再抽出し、実stdio接続で照会した結果は`uncertain`、関係4行でした。`echo`、`log_operation`、`perform_request`、`spam`を介し、相手はすべて`src/views/Communication.svelte`です。解析root全体では20 parsed／0 failed／22 skipped、60 documentのうち22 incomplete、commandは8件、保持した契約辺は12件でした。

今回の抽出依存には引き続きSvelte grammarがなく、呼び出し側の`Communication.svelte`には`incomplete`が残りました。候補の属性表記を認識できることと、相手ファイルを完全に解析できることを分け、返却関係にもその状態を残します。CoreがSvelteを一律に非対応という意味ではありません。

同じsnapshotをCodex CLIから照会する場合は、前述のCLI導入・ログイン後に次を実行します。モデル利用枠を使います。

```sh
.venv/bin/python codex_demo.py \
  --codex .codex-cli/node_modules/.bin/codex \
  --snapshot tauri-api-snapshot.json \
  --path src-tauri/src/cmd.rs \
  --report codex-public-tauri-local.json
```

Codex CLI 0.167.0の実呼び出しでも2ツールが成功し、返却値・最終回答をsnapshotと照合しました。回答は次のとおりです。

```json
{"query_status":"uncertain","related_files":["src/views/Communication.svelte"],"current_state_or_merge_safety_proven":false}
```

4つのcommandに関する関係は4行ありますが、相手ファイルは1つです。Codexへ渡した後も、解析の不完全さを`observed`へ読み替えず`uncertain`を保持しました。限定した記録は[`codex-public-tauri-verification.json`](codex-public-tauri-verification.json)です。CLIの交渉protocol版は収集しておらず、SDKで測定した版とは区別します。

これはアプリの実行や安全性、全repoの解析完全性を検証する手順ではありません。SDKの限定した記録は[`public-tauri-verification.json`](public-tauri-verification.json)です。

## 検査と限界

`export_snapshot.py`は、保存前にserverと同じ形式検査と5MiBのUTF-8サイズ上限を適用します。スキーマの対象外のパスや大きすぎる結果は、出力ファイルを作成・置換する前に拒否します。POSIXでは有効でも、この例では受け付けないパス表記があります。保存境界の検査は`.venv/bin/python -m unittest -v test_export_snapshot.py`で実行できます。

`verify.py`は4つの合成snapshotについて実stdio通信を検査します。解析状態・不正なメタデータ・重複ID・存在しないendpoint・パスの逸脱・limit・長いUTF-8パスの出力上限も確認します。
snapshotの上限は5MiB、問い合わせ結果は最大20行、JSON本文は32KiBまでです。切り詰めた場合は`truncated`と全関係行数を返します。MCPメッセージ全体のフレームサイズを32KiBとする意味ではありません。

重要な範囲は以下です。

- Tauriのapp_command、alters/queriesだけを照会する実験です。Coreの他のresourceやSQL上の衝突判定を実装したものではありません。
- snapshotは固定です。作成後の編集、dirty tree、異なるworktreeの状態を追跡しません。常に`current_worktree_verified: false`と`current_state_or_merge_safety_proven: false`を返します。
- 登録表、型、capability、実行時のTauri動作、マージの正しさは検証しません。
- ファイル名・コマンド名も機密情報になり得ます。本文を除いても「情報がない」とは言えません。ホストが結果をLLMへ送るかどうかは、そのホストの設定と運用に依存します。 このMCPが本文を返さないことと、Codex自身のファイル読み取り権限は別です。他のツールのアクセスは別途制御・確認します。
- snapshotは起動する人が選ぶデータです。返る名前は信頼された指示ではありません。結果を読むエージェントにも、repo由来のデータとして扱わせる必要があります。
- 大規模repoの性能、全MCPホストとの互換、永続的なIDE登録、production用途の完全な隔離は今回測定していません。Coreホスト版も停止中です。

参考：[MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)、[stdioの実行方法](https://py.sdk.modelcontextprotocol.io/run/)。
