---
title: "CodexにRustとTypeScriptの関係を引かせる――契約グラフをMCPへ切り出す"
emoji: "🔎"
type: "tech"
topics: ["mcp", "codex", "tauri", "rust", "python"]
published: true
---

Rustのコマンド名を変える前に、TypeScript側のどのファイルを一緒に確認すればよいか。

Tauriのように言語をまたぐ構成では、フロントからRustの関数を直接`import`するわけではありません。コマンド名という文字列を介して呼び出すため、言語内の参照検索とは別に、その対応を見る入口がほしくなります。

個人開発していたVeripsa Coreには、こうした関係を契約のグラフへ変換する実装があります。その出力の一部を、コーディングエージェントから問い合わせるローカルMCPへ切り出しました。公式例で見つかったimport属性の見落としも、[CoreのPR #4](https://github.com/RollNuts/veripsa/pull/4)で修正しています。

用意したツールは`graph_summary`と`tauri_related_files`の2つです。保存済みの解析結果を読み、ソース本文ではなく、関係するファイルとその根拠を返します。

これはローカルadapterの再現例で、出荷済みMCP製品ではありません。Coreのホスト版は停止中です。この例はDB、Webhook、GitHub Appを起動しません。

[再現コード](https://github.com/RollNuts/zenn-content/tree/0477e7e786006dcdc1e6f3edf97916b21812fdb1/examples/core-local-mcp)は、adapter、合成snapshot、SDKのClientから実serverを呼ぶスクリプトをまとめています。Codex CLIから2ツールを実際に呼ぶ動作も確認しました。

同梱の4つの合成snapshotは旧Core `d22d44f`で作成した固定データです。SDKデモとCodex CLIの既存接続記録は、このデータを使った結果です。実repoの抽出には、import属性対応後の上記公開固定Coreを使います。

## まずMCPで呼び出してみる

GitとPython 3.12を用意し、次の手順で実行します。検証環境はmacOS／Python 3.12.13でした。

```sh
git clone https://github.com/RollNuts/zenn-content.git
git -C zenn-content checkout 0477e7e786006dcdc1e6f3edf97916b21812fdb1
cd zenn-content/examples/core-local-mcp
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python client_demo.py
.venv/bin/python verify.py --report wire-verification.json
```

`requirements.txt`で直接指定する依存は`mcp==2.3.0`です。`client_demo.py`は同梱の正例を使い、serverを子プロセスで起動し、2つのツールを呼んでJSONを表示します。既定ではRustファイルを指定し、TS側の確認候補を返します。`verify.py`は4ケースと境界条件を検査し、結果を保存します。parserをserver起動時に入れる必要はありません。

この表記はPOSIX用です。Windowsでは仮想環境の`Scripts`以下を使います。依存の取得にはネットワークを使いますが、問い合わせ対象は読み込んだローカルsnapshotです。

## Codexから呼ぶ手順も確かめる

SDKのデモに加え、Codex CLI 0.167.0からも実際に2つのMCPツールを呼びました。こちらはログイン済みのCodexアカウントが前提で、モデル利用枠を使います。先ほどのSDKだけの再現には、モデル呼び出しはありません。

既存のCLIを置き換えずに固定版を用意する例です。Node.js/npmのあるmacOS環境で検証しています。

```sh
npm install --prefix .codex-cli --no-audit --no-fund --ignore-scripts @openai/codex@0.167.0
.venv/bin/python codex_demo.py --codex .codex-cli/node_modules/.bin/codex --report codex-verification-local.json
```

`codex_demo.py`は一時workspaceで、`--ignore-user-config`、`--ephemeral`、read-only sandboxを指定します。MCP設定は一回の起動引数として渡し、`codex mcp add`や設定ファイルへの書き込みは行いません。設定項目は[OpenAI公式のMCP設定](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、非対話起動は[公式ガイド](https://learn.chatgpt.com/docs/non-interactive-mode)を参照しました。

モデルには`graph_summary`、続いて`tauri_related_files`を呼ぶように指示しました。返った回答は次のとおりです。

```json
{
  "query_status": "observed",
  "related_files": ["src/client.ts"],
  "current_state_or_merge_safety_proven": false
}
```

最終回答だけでは、モデルが推測で返した可能性が残ります。そのためCodexの記録に2件の`mcp_tool_call`があり、両方が成功し、引数・返却値・回答が固定snapshotと一致することまで確認しました。この検証ではshellやファイル読み取りのtool itemは観測されませんでした。この事後検査を、ほかのツールを使えなくする強制隔離とは説明しません。

生ログにはローカルパスやアカウントの情報が含まれ得るため、公開する確認記録はCLI版、成功したツール名、検証済み回答へ絞りました。Codexが結果をモデルへ渡す点は、ローカルMCPの保存境界とは別に考える必要があります。

## 同じコマンド名を、共通の確認先にする

再現用のRust側には、次のような宣言を置きます。

```rust
#[tauri::command]
pub fn receipt_label(count: u32) -> String {
    format!("FIXTURE_BODY_TEXT_SHOULD_STAY_OUT_OF_GRAPH: {count}")
}
```

フロント側では、公式APIから`invoke`を読み込みます。

```ts
import { invoke } from "@tauri-apps/api/core";

export async function requestLabel() {
  return invoke("receipt_label", { count: 3 });
}
```

CoreのTauri抽出器は、明示的な`#[tauri::command]`または同じmoduleの明示importに由来する属性と、公式API由来の`invoke`に直接渡した既知の名前を手掛かりに、共通の`app_command`へ辺を張ります。

```text
src-tauri/commands.rs ──alters──▶ tauri_command::receipt_label
src/client.ts         ──queries─▶ tauri_command::receipt_label
```

`alters`と`queries`はグラフ上の役割名です。Rustコマンドの副作用や、読み取り専用かどうかを解析した結果ではありません。

Rust側を指定すると、同じ契約につながるTS側を確認候補にできます。その後、実コードで引数・戻り値・呼び出し条件を調べます。

Tauriアプリで実行するには、コマンドを`invoke_handler`へ登録する工程もあります。宣言・登録・呼び出しの流れは[公式ガイド](https://v2.tauri.app/develop/calling-rust/#basic-example)にあります。この再現例は、登録やIPC実行を検証するものではありません。

## 解析と問い合わせを、別の時間に行う

最初からMCPの呼び出しごとにrepo全体を解析する構成にはしませんでした。処理を2段階に分けています。

1. 固定したCoreで、手元の入力からメタデータsnapshotを生成する。
2. MCP serverは起動時にそのsnapshotを読み、問い合わせに答える。

解析の入口は、公開Coreの`code_graph_extract.build_graph`です。対象は[commit `9b5429aac861164cc1b41278dcaf540fa6fabad7`](https://github.com/RollNuts/veripsa/tree/9b5429aac861164cc1b41278dcaf540fa6fabad7)へ固定し、再現コードで使う抽出パイプラインのblobも照合します。

`build_graph`の返り値は丸ごと流さず、`app_command`、`alters`／`queries`、ファイルの解析状態だけに絞りました。ほかのresourceやSQL側のPR交通判断は扱いません。

保存前にはMCP側と同じ形式検査と5MiBのUTF-8サイズ上限を適用します。抽出が終わっても、serverが読み込めない形式のsnapshotは書き出しません。

抽出時には本文を読みます。一方、保存する小さいsnapshotでは、必要な相対パス、契約ID、役割、曖昧さや解析状態などを選びます。関数本文や、元のグラフにある絶対rootをそのまま配る構成にはしません。

MCPのツールからは、任意のディレクトリを解析する指示を受けません。`path`は、読み込んだsnapshotの中を照会する識別子です。問い合わせ時に、そのパスのソースファイルを開く処理もありません。

## 2つのツールが返すもの

### graph_summary

最初に、何を読んだ結果なのかを確認します。`graph_summary`は入力引数を持たず、保持したdocument・command・契約辺の件数、各解析状態、snapshotの識別情報を返します。抽出件数と`analysis_status`は別に扱います。ファイルの存在やgraphの形だけでは、解析の完全性を判断できないためです。

同梱した正例をSDKのClientから呼んだ結果の抜粋です。

```json
{
  "query_scope": "tauri_app_command_metadata_only",
  "files_parsed": 2,
  "files_failed": 0,
  "files_skipped": 0,
  "document_count": 2,
  "tauri_command_count": 1,
  "retained_contract_edge_count": 2,
  "ambiguous_command_count": 0
}
```

### tauri_related_files

次に、変更する予定のRustファイルを指定します。引数の例は次のとおりです。

```json
{
  "path": "src-tauri/commands.rs",
  "limit": 20
}
```

相手のファイルに加えて、共有するresource、双方の役割、参照・解析状態を返します。同じ`tauri_command::receipt_label`へ向かう、という候補の根拠が分かります。

今回のquery serviceでは、関係の状態を`observed`と`uncertain`で表します。曖昧なcommandや参照、解析状態のmarkerがあれば、確定した関係と混ぜずに`uncertain`として残します。

実際に`src-tauri/commands.rs`を指定すると、次の関係が返りました。共通のsnapshot情報などは省略しています。

```json
{
  "status": "observed",
  "relations": [
    {
      "resource": "tauri_command::receipt_label",
      "related_file": "src/client.ts",
      "target_role": "alters",
      "peer_role": "queries",
      "evidence_status": "observed"
    }
  ],
  "total_relation_rows": 1,
  "truncated": false,
  "current_state_or_merge_safety_proven": false
}
```

結果件数には上限を設け、切れた場合は`truncated`と全relation行数を返します。結果の一部だけを返しているのに、すべて調べ終わったように見せないためです。この上限は結果表示の制約であり、グラフ全体の正しさを保証するものではありません。

## 空の結果を「依存なし」にしない

MCPへ載せるときに残したかったのは、辺だけでなく、辺を使える範囲でした。そこで、呼び方と定義数を変えた4ケースのsnapshotを使って確認しました。

正例に加え、自前の同名関数、変数で渡す名前、Rustの別ファイルにある同名定義を比較します。

たとえば`const command = "receipt_label"; invoke(command)`は、人間には名前が分かります。しかし、この抽出器は定数伝播をしません。今回のqueryで候補が出なかったとしても、実際に依存していないとは言えません。

Tauri API自体の`cmd`は`string`です。変数での呼び出しをTauriが禁止しているという話ではなく、[APIの仕様](https://v2.tauri.app/reference/javascript/api/namespacecore/#invoke)と、今回の抽出範囲を分けています。

重複定義のケースでは、Coreが残した曖昧さをquery serviceでも扱います。これは「実行先を決めてくれる」という結果ではありません。どの候補を人間が読み比べる必要があるかを、証拠とともに返すための状態です。

4ケースの検査では、比較のためTS側の`src/client.ts`を指定しました。先ほどのRust→TSのデモとは逆向きで、次の結果になりました。

| ケース | status | relation行数 |
| --- | --- | ---: |
| official-literal | observed | 1 |
| local-invoke | not_observed | 0 |
| dynamic-name | not_observed | 0 |
| duplicate-command | uncertain | 2 |

duplicate-commandで返った2件は、同名commandを持つ2つのRustファイルです。重複した定義を1つの確定先へ絞り込んだ結果ではありません。

stdio経由では、各ケースで3種類の不正pathと上限外の`limit`を拒否することも確認しました。

さらに、10件のローカル境界チェックを実行しました。未知の解析状態や不正なメタデータ、重複document／command、存在しないnodeを参照する辺の拒否、不完全な相手の`uncertain`保持、UTF-8で32KiBの応答上限と切り詰め、未知pathの照会で内部indexが増えないことなどを扱います。このbyte上限検査はquery serviceを直接呼びます。

加えて、長いUTF-8パスを持つ合成snapshotを、実stdio接続でも検査しました。61件の関係に対して11件を返し、`truncated: true`となりました。返却されたtext本文は31,124 bytesで、32,768 bytesの上限内でした。MCP message全体のframeサイズを32KiBに制限した、という意味ではありません。

## 公式Tauri例で、見つかった関係にも解析状態を残す

[公式Tauriの固定commit](https://github.com/tauri-apps/tauri/tree/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api)の`examples/api`には、[importした`#[command]`による`perform_request`の定義](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/src/cmd.rs#L44)、[Svelte内TypeScriptの`invoke('perform_request', ...)`](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src/views/Communication.svelte#L28)、[handler登録](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/src/lib.rs#L158)があります。

旧固定Core `d22d44f`では、Rustファイル`src-tauri/src/cmd.rs`の照会は`not_observed`、関係行数0でした。この版は明示的な`#[tauri::command]`だけを定義として扱い、importされた`#[command]`を拾えなかったためです。

Core側にはRustの構文木によるimport解決を加えました。同じmoduleが直接importした`tauri::command`、alias、入れ子groupに対応し、無関係なbare属性や他moduleのimportを採用しません。glob、reexport、macro展開、cfg評価の解決は今回の範囲に含めません。

更新後の固定Coreから同じ公式入力を再抽出し、SDKのstdio接続で照会すると、`uncertain`、関係4行が返りました。`echo`、`log_operation`、`perform_request`、`spam`を介し、相手はすべて`src/views/Communication.svelte`でした。アプリのbuildや起動は行っていません。

今回の依存定義には引き続きSvelte grammarがありません。呼び出し側のdocumentには`incomplete`が残り、返却した関係も`uncertain`を保ちました。候補が出ることと、完全な解析や安全な変更を証明できることを分けるためです。コマンドと件数は[再現手順と記録](https://github.com/RollNuts/zenn-content/tree/0477e7e786006dcdc1e6f3edf97916b21812fdb1/examples/core-local-mcp#公式tauri例でimport対応と解析状態を確認する)へまとめます。

## Pythonの関数と、MCPの境界を分ける

関係を組み立てる処理は、`query_service.py`の`SnapshotQueries`に置きました。MCP側はその関数を呼び、結果を返す層です。

```python
@server.tool(annotations=annotation)
def graph_summary() -> dict:
    return queries.summary()

@server.tool(annotations=annotation)
def tauri_related_files(path: str, limit: int = 20) -> dict:
    return queries.related_files(path, limit)
```

上は構成を示す抜粋です。実装では入力の検査、エラー変換、ツールの説明も付けています。`read_only_hint`などのannotationは、ツールの意図をclientへ伝えるものです。annotationを書いたことを、読み取り範囲の強制やsandboxの代わりにはしていません。

MCPには[公式Python SDKの`mcp==2.3.0`](https://pypi.org/project/mcp/2.3.0/)を使います。stdioではclientがserverを子プロセスとして起動し、標準入出力でMCP messageをやり取りします。通常のCLIのように診断文字列を`stdout`へprintすると、通信へ混ざるため、プロトコルとlogの出力先を分ける必要があります。[stdioの公式仕様](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)も参照できます。

SDKの`Client`と`StdioServerParameters`から実serverプロセスを起動し、2つのツールの一覧、引数付き呼び出し、返却payloadを検査しました。

SDKは2.3.0で、通常の接続ではprotocol 2026-07-28を確認しました。`client_demo.py --legacy`では`initialize`による2025-11-25の接続と2ツールの呼び出しも成功しています。これはSDK 1.x全般や全ホストへの互換保証ではありません。4つのstdioケース、10件のローカル境界チェック、UTF-8本文の上限検査も成功しました。Codex CLIの確認は前述の別検証で、永続的なアプリ・IDE設定は今回導入していません。

## 自分のrepoへ使う場合

自分でsnapshotを作る場合だけ、抽出用依存と固定Coreを追加します。

```sh
git clone https://github.com/RollNuts/veripsa.git core
git -C core checkout 9b5429aac861164cc1b41278dcaf540fa6fabad7
.venv/bin/python -m pip install --only-binary=:all: --no-deps -r requirements-extract.txt
.venv/bin/python export_snapshot.py \
  --core core \
  --repo /ABSOLUTE/PATH/TO/TARGET \
  --out snapshot.json
```

`TARGET`は解析するローカルディレクトリです。この操作では本文を解析してsnapshotを書き出すので、まず同梱例を確認してから、扱う情報を選びます。Coreは別途取得し、コードを変更せず使います。ライセンスはBusiness Source License 1.1のsource-availableです。

MCP hostへ追加する場合は、絶対パスのPythonと`server.py --snapshot /ABSOLUTE/PATH/TO/snapshot.json`を起動引数へ指定します。serverは通信待ちになり、対話画面は出ません。Codexの一回限りのCLI実行は上の手順で確認済みです。各アプリ・IDEへ永続登録する場合は、その設定・動作を別に確認してください。

## 返せた情報と、まだ証明していないこと

返却には、`current_state_or_merge_safety_proven: false`を含めています。snapshotのSHA-256は読み込んだJSONを識別するもので、現在の作業ツリーと一致するという証明ではありません。server起動後にコードを変更しても、保存済みの解析結果が自動で更新される構成ではありません。

また、「本文を返さない」と「情報を何も返さない」は異なります。ファイルパス、契約名、関係だけでも、開発内容を表すことがあります。stdioで手元のserverとつないでも、その結果をclientがどのmodelへ渡すかは別の境界です。ローカルserverだからLLMへの送信もない、とは説明しません。

今回できるのは、保存した解析範囲の中から、次に読むファイルの候補と根拠を返すことです。Tauriのすべての呼び出し形式、引数・戻り値の型、実行時の正しさ、現在のPR同士の衝突や安全なmergeを判定するものではありません。

解析器へAPIを付けるときは、入力と出力、対象の時点、分からない場合の表現も一緒に切り出す。その境界を再実行できる形で残しました。

本稿と再現コードの作成には、コーディングエージェントを利用しています。
