---
title: "CodexにRustとTypeScriptの関係を引かせる――契約グラフをMCPへ切り出す"
emoji: "🔎"
type: "tech"
topics: ["mcp", "codex", "tauri", "rust", "python"]
published: true
---

Rust側のTauriコマンド名を変えたとき、TypeScript側のどこを一緒に確認すればよいか。AIにコードを読ませた結果だけで、呼び出し・登録・権限まで確認できたと言ってよいか。

たとえば`perform_request`を改名するなら、フロントの`invoke("perform_request", ...)`だけでなく、Rustのhandler登録や権限識別子の参照も確認対象になります。文字列検索で見つかる接点もありますが、別表記の識別子を追う追加調査が必要な場合もあります。

個人開発してきたVeripsa Coreの解析結果を、AIから照会するローカルMCPへ切り出しました。中心はMCPではなく、コードを読み、関係と解析状態を残す基盤です。MCPはその一部を問い合わせる入口です。

今回、公式Tauri例の1コマンドでは、参照を追った検索が5つの確認先を含み、MCPのsnapshot照会だけでは1ファイルで`uncertain`でした。通常AIとCore併用も各1回試しましたが、両方とも5確認先を含みました。**この例では、Coreを加えて見落としやツール呼び出しを減らしたとは実証できていません。** いま確認できるのは、限定した接点と解析状態をAIへ渡し、ソース確認へ戻れることです。

```text
perform_request の変更前に確認する接点（公式例）
├─ フロントの invoke      → Core MCPが候補を返す（uncertain）
└─ handler・build・権限   → 今回のMCP出力には出ない。別途確認する
```

[再現コードと検証記録](https://github.com/RollNuts/zenn-content/tree/89fe0fe12258c827a9e7fc54cb12fc96401018de/examples/core-local-mcp)には、従来のSDK・Codex実測を固定版として残しています。今回追加した[検索との比較コード](https://github.com/RollNuts/zenn-content/tree/4b0f00441b4cee3cded29813d9bdb241c4b45722/examples/core-local-mcp#検索とmcpの比較)と結果は、後半の手順から再実行できます。Coreのホスト型GitHub Appは2026年8月18日から停止中です。この記事の手順ではDB・Webhook・Appを起動しません。

## 変更前に何を探すのか

まず解く問いを、「TauriのIPCコマンドを変える前に、一緒に確認するファイルを探す」まで絞ります。バグの自動修正や、変更後のアプリが動くことの保証ではありません。

文字列検索は、名前がそのまま残っている定義・呼び出し・登録を見つける有力な方法です。一方、一致した文字列が同じ契約かどうか、別の識別子へ変換されていないかは、ソースを読む必要があります。検索範囲や除外設定でも結果は変わります。「検索では発見できない」と一般化する根拠はありません。

Coreのこの実装は、Rustのcommand定義と、公式Tauri API由来の既知の`invoke`名から、共通の契約への接点を抽出します。保存したsnapshotをMCPへ渡し、関係するパス、根拠、解析の不完全さをまとめて照会します。コード本文を毎回返す処理ではありませんが、完全な変更影響解析でもありません。

## RustとTypeScriptを、同じ契約の接点として扱う

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

## 解析と問い合わせを分け、結果を再利用する

最初からMCPの呼び出しごとにrepo全体を解析する構成にはしませんでした。処理を2段階に分けています。

1. 固定したCoreで、手元の入力からメタデータsnapshotを生成する。
2. MCP serverは起動時にそのsnapshotを読み、問い合わせに答える。

解析の入口は、公開Coreの`code_graph_extract.build_graph`です。対象は[commit `9b5429aac861164cc1b41278dcaf540fa6fabad7`](https://github.com/RollNuts/veripsa/tree/9b5429aac861164cc1b41278dcaf540fa6fabad7)へ固定し、再現コードで使う抽出パイプラインのblobも照合します。

`build_graph`の返り値は丸ごと流さず、`app_command`、`alters`／`queries`、ファイルの解析状態だけに絞りました。ほかのresourceやSQL側のPR交通判断は扱いません。

保存前にはMCP側と同じ形式検査と5MiBのUTF-8サイズ上限を適用します。抽出が終わっても、serverが読み込めない形式のsnapshotは書き出しません。

抽出時には本文を読みます。一方、保存する小さいsnapshotでは、必要な相対パス、契約ID、役割、曖昧さや解析状態などを選びます。関数本文や、元のグラフにある絶対rootをそのまま配る構成にはしません。

MCPのツールからは、任意のディレクトリを解析する指示を受けません。`path`は、読み込んだsnapshotの中を照会する識別子です。問い合わせ時に、そのパスのソースファイルを開く処理もありません。

## AIへ渡すのは、関係とその観測範囲

このquery serviceでは、有効な問い合わせの結果を次のように区別します。確率として校正したスコアではなく、観測範囲と証拠の状態を伝えるラベルです。

| 状態 | 何を意味するか | AIが判断してはいけないこと |
| --- | --- | --- |
| `observed` | 対象snapshotの範囲で関係を観測した | 実行先や変更後の動作が保証された |
| `uncertain` | 不完全または曖昧な解析情報が残る | 候補が出たので完全に解析できた |
| `not_observed` | 対象範囲で関係が観測されなかった | 依存が存在しない、変更して安全 |

ツールの起動失敗や不正入力は、この3状態とは別のエラーです。失敗、未測定、有効な空の結果を混ぜません。

AIが1件の候補を「影響先はこの1件だけ」と読み替えると、登録や権限の確認を落とすおそれがあります。このため返却には`current_state_or_merge_safety_proven: false`を含めます。ただし、フィールドを返しただけでAIの判断を強制できるわけではありません。モデルが実際にどう扱うかは、別に検証する必要があります。

次に読む対象を案内するには、辺だけでなく「いつの入力か」「どこまで解析できたか」「何を観測しなかったか」を一緒に返す必要があります。この試作が確かめているのは、その根拠の品質を保つ境界です。

### 2つのツールが返すもの

#### graph_summary

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

#### tauri_related_files

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

## 実際のTauri例を検索と比べる

[公式Tauriの固定commit](https://github.com/tauri-apps/tauri/tree/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api)にある`perform_request`を対象にしました。問いは、`src-tauri/src/cmd.rs`以外にどのファイルを確認するかです。実際の改名、ビルド、IPC実行、権限の変更は行っていません。

結果を見る前に、AI支援のソース確認と別レビューで、次の5確認先を選びました。全repoの網羅的な正解ラベルではなく、すべてのファイルを編集しなければならない、という意味でもありません。

| 確認先（`examples/api`からの相対パス） | ソース上の確認理由 |
| --- | --- |
| `src/views/Communication.svelte` | [公式APIの呼び出し](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src/views/Communication.svelte#L27-L36) |
| `src-tauri/src/lib.rs` | [handlerへの登録](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/src/lib.rs#L158-L163) |
| `src-tauri/build.rs` | [AppManifestのcommand宣言](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/build.rs#L16-L21) |
| `src-tauri/permissions/autogenerated/perform_request.toml` | [command名とallow／deny識別子の対応](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/permissions/autogenerated/perform_request.toml#L1-L11)。生成物なので手編集を勧めない |
| `src-tauri/capabilities/run-app.json` | [allow識別子の参照](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/capabilities/run-app.json#L17) |

### A：文字列検索では、見つかった識別子を追う

`examples/api`全体で、ripgrepの通常の除外設定を使って検索します。

```sh
rg -n -F -- perform_request .
```

起点の`cmd.rs`を除くと4ファイルが見つかり、capabilityのJSONは含まれませんでした。ただし、そこで検索を止める比較にはしません。最初の結果にある生成TOMLを読み、対応する`allow-perform-request`を得て参照を追うと、5つ目の確認先が見つかりました。

```sh
rg -n -F -- allow-perform-request .
```

追加の検索語は最初の検索結果から取得しています。チェックリストから答えを検索へ与えたわけではありません。

### C：準備済みCore snapshotを、実MCP接続で照会する

既存のPython SDKから実serverを起動し、`graph_summary`と`tauri_related_files`を呼びました。起点ファイルの問い合わせ結果は4command由来の4関係行で、重複を除くと相手は1ファイルです。比較コードでは、そのうち`tauri_command::perform_request`の行を選んで集計しています。command単位の検索APIを新設したものではありません。

| 方法 | 候補ファイル数 | 選定5確認先に含まれた数 | 選定確認先で含まれなかったもの |
| --- | ---: | ---: | --- |
| A：コマンド名の文字列検索 | 4 | 4 | capabilityのJSON |
| A：見つかった権限識別子の参照も追跡 | 5 | 5 | このチェックリストでは無し |
| C：Core MCPの準備済みsnapshot照会 | 1 | 1 | handler登録、build宣言、生成permission、capability |

Cの1候補は`Communication.svelte`で、`uncertain`を保持しました。Svelte側の解析状態が`incomplete`だからです。登録・build・権限は、今回のTauri契約投影と2ツールのモデル化範囲ではありません。Coreの全解析機能を使った影響調査を評価した結果ではありません。

今回の各候補集合に、選定リスト外のファイルはありませんでした。ただし、全ファイルの正誤をラベル付けしていないため、一般的な誤検知率・precision／recallは算出しません。候補が見つかったことと、必要な修正を網羅したことも区別します。

### 呼び出し回数と時間の扱い

Aは`rg`を2回起動し、途中で生成TOMLを1回読みました。Cは1つのstdio sessionで初期化・`tools/list`を行い、2つのtoolを呼びました。シェル実行の数とMCP toolの数は同じ単位ではありません。

macOS・Python 3.12.13・ripgrep 15.2.0・MCP SDK 2.3.0の1実行では、Aの検索2回とTOML読み取りは約0.020秒、Cの接続と2toolは約0.325秒でした。これは**機械の実行時間**で、人の調査時間ではありません。Cは準備済みsnapshotを読み、Coreの抽出コストを含みません。セットアップや確認先の選定も除いているため、この値から生産性や速度の優位は判断しません。時間は安定した結果JSONと分けて保存しています。

### B：通常AIと、C1：Coreを併用するAIも各1回試した

検索・SDKだけの比較とは別に、Codex CLI 0.167.0で、同じ課題と共通プロンプトを使う2試行を行いました。Bは通常のソース調査、C1は同じソース調査にCore MCPを追加した条件です。C1もMCPの結果だけで止めず、ソースを読んで不足を補うことを許しています。

共通プロンプトには「Coreが使える場合は先に2ツールを呼ぶ」という条件文を入れ、5確認先のリストは与えていません。同じ固定Git archiveから別々の一時workspaceを作り、read-only・一時実行・web検索無効で、アプリのbuild／test／importやファイル変更を行わず調査させました。実行後のコマンドログも、ソースの読取・検索だけだったことを確認しています。

| 条件 | 返したpeerパス数 | 選定5確認先の包含 | 選定外で未評価の候補 | shell tool呼出 | MCP tool呼出 | CLI経過秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B：通常AIのソース調査 | 7 | 5 | 2 | 3 | 0 | 29.14 |
| C1：Core MCP＋ソース調査 | 6 | 5 | 1 | 3 | 2 | 31.05 |

どちらも選定5確認先を含み、この1例ではCore追加による見落としの減少は観測しませんでした。shell toolの1呼出には複数の検索・読み取りコマンドが入るため、先ほどの`rg`起動回数と同じ単位ではありません。選定外の`tauri.conf.json`やisolation hookは、command pruningやIPC経路の背景確認として挙げられており、自動的に誤検知とは数えません。

B/C1とも、最終JSONの`claims_complete`と`merge_safety_proven`は`false`でした。C1は不完全なsnapshotをソースと照合したという留保も残しました。ただし、両方へ完全性・安全性を断定しない指示を与えています。これをCoreだけの効果や、通常のAIが誤断定する割合の測定とはしません。

**条件の限界もあります。** 同じCLIのdefaultを依頼しましたが、受信イベントには解決されたmodel IDが出ず、厳密な同一modelの確認はできていません。B→C1の固定順で各1回、順序の入替や反復も無しです。経過秒はqueue・model応答・toolを含む機械時間で、上の差から速度や生産性の優位を推定しません。既存の「MCPだけを呼ばせたCodex成功記録」を、通常AIの対照群に流用してもいません。

[共通プロンプト](https://github.com/RollNuts/zenn-content/blob/4b0f00441b4cee3cded29813d9bdb241c4b45722/examples/core-local-mcp/agent-comparison-prompt.txt)と[限定した結果記録](https://github.com/RollNuts/zenn-content/blob/4b0f00441b4cee3cded29813d9bdb241c4b45722/examples/core-local-mcp/agent-comparison-receipt.json)を公開しています。生のコマンド出力・account情報・ローカル絶対パスは公開しません。このAI試行は既存のChatGPT利用枠を使う任意の検証で、SDKだけの再現ではモデルを呼びません。

### 入力と、比較を再実行する手順

Coreは`9b5429a`、Tauriは`2e23492`へ固定しています。現在のCore main `4236848`でも、再現例が固定する24のproductionソースblobが同一であることを確認しました。古い版のCodex成功記録を、新しい条件での成功へ読み替えてはいません。

snapshot自身にはTauriのcommit SHAが埋め込まれていません。比較コードは固定sourceの清浄さとGit tree、snapshotの正確なSHA-256を別々に記録します。今回は同じ固定sourceから再抽出し、作成時刻以外が元snapshotと一致することも確認しました。一般にsnapshotの識別子だけで、手元のソースとの対応が証明されるわけではありません。

比較コードは、後半で使う旧固定版`89fe0fe`にはありません。**今回の比較用には別のcheckoutを用意します。** 以下は追加コードを含む固定版を使い、公式Tauriからsnapshotを生成してから照会する、一続きの手順です。

```sh
git clone https://github.com/RollNuts/zenn-content.git zenn-comparison
git -C zenn-comparison checkout 4b0f00441b4cee3cded29813d9bdb241c4b45722
cd zenn-comparison/examples/core-local-mcp
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
git clone https://github.com/RollNuts/veripsa.git core
git -C core checkout 9b5429aac861164cc1b41278dcaf540fa6fabad7
.venv/bin/python -m pip install --only-binary=:all: --no-deps -r requirements-extract.txt
git clone https://github.com/tauri-apps/tauri.git tauri-source
git -C tauri-source checkout 2e23492ab9bcec06bab041e0e47447aaa0da298c
.venv/bin/python export_snapshot.py \
  --core core --repo tauri-source/examples/api --out tauri-api-snapshot.json
.venv/bin/python compare_search.py \
  --tauri tauri-source --snapshot tauri-api-snapshot.json \
  --timings comparison-timings-local.json > comparison-evidence-local.json
.venv/bin/python -m unittest -v test_compare_search.py test_compare_agents.py
```

Gitやripgrepを独自の場所へ導入した場合は`--git`と`--rg`を指定します。clone・依存取得はネットワークを使います。その後の抽出と`compare_search.py`はローカルで動き、モデル・DBを呼ばず、Tauriアプリも実行しません。snapshotの作成時刻が異なれば、そのファイルのSHA-256も変わるので、結果JSONは候補・状態・固定source IDを分けて確認します。

AI側の2試行を自分で再実行する場合だけ、[compare_agents.pyの手順](https://github.com/RollNuts/zenn-content/tree/4b0f00441b4cee3cded29813d9bdb241c4b45722/examples/core-local-mcp#通常aiとcore併用の単発比較)を使います。CLI版・入力条件を確認する既定のpreflightはモデルを呼ばず、明示的な`--run`でだけ既存ChatGPT利用枠を使うB/C1を各1回実行します。生ログの保存先はGit repo外の新規private directoryに指定し、そのまま公開しないでください。

## 既存手法との違いと使い分け

この比較は検出精度の順位ではなく、解く問題の違いです。以下の他ツールは公式資料を調査したもので、同条件での導入・性能測定はしていません。

| 手段 | 主に解く問い | 導入と、今回のCore MCPとの違い |
| --- | --- | --- |
| [Tauri Specta](https://specta.dev/docs/tauri-specta) | Rustのcommandを、型の合うTS／JSからどう呼ぶか | 注釈・command登録・生成処理を組み込み、型付きbindingを使う。呼び出し側の契約を整える方法で、既存コードから接点を探す今回の解析とは役割が異なる |
| [LSP／LSIF](https://microsoft.github.io/language-server-protocol/) | この記号の定義・参照先はどこか | LSPは言語機能を提供する通信規約。言語間連携や解析・cacheはserverの実装による。保存索引の別規格LSIFもあり、「LSPは保存・言語横断ができない」とは言えない |
| [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) | ソースはどのような構文構造か | ソースを書き換えず構文木を作り、増分解析もできる。ファイル間・言語間の契約を結ぶ処理は利用側が実装する。Coreもこの層を利用する |
| [ripgrep](https://github.com/BurntSushi/ripgrep)等のコード検索 | この文字列・パターンはどこか | ソース変更不要で、一致箇所を発見できる。今回は識別子を追う追加検索も有効だった。一致だけで同じ契約と確定するわけではなく、検索範囲や除外設定にも注意する |
| [CodeGraphContext](https://codegraphcontext.github.io/reference/mcp/) | 保存したコードグラフをどう調べ、AIへ渡すか | CLI／MCPによる索引・問い合わせや更新監視があり、[解析済みbundleの再利用](https://codegraphcontext.github.io/guides/bundles/)もある。グラフの保存・再利用・MCP提供自体をCore独自とは説明できない |

Tauri Spectaのように、型付きbindingを導入して呼び出しを整える方が目的に合う場合もあります。既存の検索・言語サーバー・グラフ製品も併用の候補です。今回示せるのは、**既存Tauriコードを変更せず、限定した契約接点と解析状態を固定snapshotから返す、小さい読取インターフェースの実証**です。これを排他的な技術優位や、他製品より正確という主張にはしません。

解析能力と起動方法も別です。各方式はCLI・CIや独自連携へ組み込めます。「GitHubで自動実行できるか」を、解析方式だけの優劣にはしません。

## MCP・CLI・GitHub Appの役割

Coreの開発は、並行作業のGitコンフリクトを減らしたいという困りごとから始まりました。MCPを中心に作り直したのではなく、既存の解析資産の一部を別の入口から使っています。

| 資産・入口 | 現在の範囲 |
| --- | --- |
| Code graph | ソースから構造・参照・resourceと解析状態を抽出する基盤。Tauriの接点もその一部 |
| Co-change | Git履歴から共変更の件数・確率・liftを求める既存実装。因果関係や将来の故障を保証しない。今回のMCPには含めていない |
| 永続化・GitHub App | グラフや履歴、PRの状態を保存し、イベントを処理する実装がある。ホスト型Appは停止中で、今回稼働を確認したものではない |
| CLI／MCP | CLIはローカル解析、今回のMCPは保存済みTauriメタデータのオンデマンド照会。MCPの2ツールからPR判定は実行しない |

詳細は[実装資産と検証範囲の一覧](https://github.com/RollNuts/veripsa/blob/4236848504c8cb2cc3c14db22408fb519b06f754/docs/ANALYSIS_ASSETS.md)で区別しています。AppはPR作成・更新イベントをきっかけに検査機会を作れる一方、MCPはAIや利用者に呼ばれなければ動きません。AppにもWebhook障害や停止の失敗条件があり、完全な実行保証ではありません。

今後共通の解析結果をCLI・MCP・Appから利用する方向は考えられますが、今回のadapterを、継続同期や自動merge制御まで提供済みの製品とは説明しません。

## 再現する：SDKとCodexの手順

### SDKだけで呼ぶ

GitとPython 3.12を用意し、次の手順で実行します。検証環境はmacOS／Python 3.12.13でした。

```sh
git clone https://github.com/RollNuts/zenn-content.git
git -C zenn-content checkout 89fe0fe12258c827a9e7fc54cb12fc96401018de
cd zenn-content/examples/core-local-mcp
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python client_demo.py
.venv/bin/python verify.py --report wire-verification.json
```

`requirements.txt`で直接指定する依存は`mcp==2.3.0`です。`client_demo.py`は同梱の正例を使い、serverを子プロセスで起動し、2つのツールを呼んでJSONを表示します。既定ではRustファイルを指定し、TS側の確認候補を返します。`verify.py`は4ケースと境界条件を検査し、結果を保存します。parserをserver起動時に入れる必要はありません。

この表記はPOSIX用です。Windowsでは仮想環境の`Scripts`以下を使います。依存の取得にはネットワークを使いますが、問い合わせ対象は読み込んだローカルsnapshotです。

### Codexからの実ツール呼び出し

SDKのデモに加え、Codex CLI 0.167.0からも実際に2つのMCPツールを呼びました。こちらはログイン済みのCodexアカウントが前提で、モデル利用枠を使います。先ほどのSDKだけの再現には、モデル呼び出しはありません。

既存のCLIを置き換えずに固定版を用意する例です。Node.js/npmのあるmacOS環境で検証しています。

```sh
npm install --prefix .codex-cli --no-audit --no-fund --ignore-scripts @openai/codex@0.167.0
.venv/bin/python codex_demo.py --codex .codex-cli/node_modules/.bin/codex --report codex-verification-local.json
```

`codex_demo.py`は一時workspaceで、`--ignore-user-config`、`--ephemeral`、read-only sandboxを指定します。MCP設定は一回の起動引数として渡し、`codex mcp add`や設定ファイルへの書き込みは行いません。設定項目は[OpenAI公式のMCP設定](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、非対話起動は[公式ガイド](https://learn.chatgpt.com/docs/non-interactive-mode)を参照しました。

モデルには`graph_summary`、続いて`tauri_related_files`を呼ぶように指示しました。まず、同梱の合成snapshotで返った回答は次のとおりです。

```json
{
  "query_status": "observed",
  "related_files": ["src/client.ts"],
  "current_state_or_merge_safety_proven": false
}
```

最終回答だけでは、モデルが推測で返した可能性が残ります。そのためCodexの記録に2件の`mcp_tool_call`があり、両方が成功し、引数・返却値・回答が固定snapshotと一致することまで確認しました。この検証ではshellやファイル読み取りのtool itemは観測されませんでした。この事後検査を、ほかのツールを使えなくする強制隔離とは説明しません。

生ログにはローカルパスやアカウントの情報が含まれ得るため、公開する確認記録はCLI版、成功したツール名、検証済み回答へ絞りました。Codexが結果をモデルへ渡す点は、ローカルMCPの保存境界とは別に考える必要があります。

## 既存の固定snapshotで確かめた境界

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

## 公式Tauri例でのSDK・Codex検証記録

[公式Tauriの固定commit](https://github.com/tauri-apps/tauri/tree/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api)の`examples/api`には、[importした`#[command]`による`perform_request`の定義](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/src/cmd.rs#L44)、[Svelte内TypeScriptの`invoke('perform_request', ...)`](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src/views/Communication.svelte#L28)、[handler登録](https://github.com/tauri-apps/tauri/blob/2e23492ab9bcec06bab041e0e47447aaa0da298c/examples/api/src-tauri/src/lib.rs#L158)があります。

旧固定Core `d22d44f`では、Rustファイル`src-tauri/src/cmd.rs`の照会は`not_observed`、関係行数0でした。この版は明示的な`#[tauri::command]`だけを定義として扱い、importされた`#[command]`を拾えなかったためです。

Core側にはRustの構文木によるimport解決を加えました。同じmoduleが直接importした`tauri::command`、alias、入れ子groupに対応し、無関係なbare属性や他moduleのimportを採用しません。glob、reexport、macro展開、cfg評価の解決は今回の範囲に含めません。

更新後の固定Coreから同じ公式入力を再抽出し、SDKのstdio接続で照会すると、`uncertain`、関係4行が返りました。`echo`、`log_operation`、`perform_request`、`spam`を介し、相手はすべて`src/views/Communication.svelte`でした。アプリのbuildや起動は行っていません。

今回の依存定義には引き続きSvelte grammarがありません。呼び出し側のdocumentには`incomplete`が残り、返却した関係も`uncertain`を保ちました。候補が出ることと、完全な解析や安全な変更を証明できることを分けるためです。コマンドと件数は[再現手順と記録](https://github.com/RollNuts/zenn-content/tree/89fe0fe12258c827a9e7fc54cb12fc96401018de/examples/core-local-mcp#公式tauri例でimport対応と解析状態を確認する)へまとめます。


READMEの手順で`tauri-api-snapshot.json`を生成した後、同じsnapshotをCodexへ渡しました。CLIの導入とログインは前述の手順を使います。

```sh
.venv/bin/python codex_demo.py \
  --codex .codex-cli/node_modules/.bin/codex \
  --snapshot tauri-api-snapshot.json \
  --path src-tauri/src/cmd.rs \
  --report codex-public-tauri-local.json
```

Codex CLI 0.167.0の2件のMCP呼び出しについて、引数・返却値・最終回答をsnapshotと照合しました。

```json
{
  "query_status": "uncertain",
  "related_files": ["src/views/Communication.svelte"],
  "current_state_or_merge_safety_proven": false
}
```

4つのcommandから得た関係は4行ありますが、相手ファイルは1つです。`related_files`は同じpathを重複除去して表示しています。Codexへ渡しても、不完全な解析を確定した関係へ読み替えず、`uncertain`を保持しました。限定した確認記録は[`codex-public-tauri-verification.json`](https://github.com/RollNuts/zenn-content/blob/89fe0fe12258c827a9e7fc54cb12fc96401018de/examples/core-local-mcp/codex-public-tauri-verification.json)です。

## Pythonの処理とMCPの境界

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

## 自分のrepoのsnapshotを作る

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

## 現時点の制約

返却には、`current_state_or_merge_safety_proven: false`を含めています。snapshotのSHA-256は読み込んだJSONを識別するもので、現在の作業ツリーと一致するという証明ではありません。server起動後にコードを変更しても、保存済みの解析結果が自動で更新される構成ではありません。

また、「本文を返さない」と「情報を何も返さない」は異なります。ファイルパス、契約名、関係だけでも、開発内容を表すことがあります。stdioで手元のserverとつないでも、その結果をclientがどのmodelへ渡すかは別の境界です。ローカルserverだからLLMへの送信もない、とは説明しません。 ここで本文を返さないのは、このMCPツールの性質です。Codex自身のファイル読み取りを一律に止めるものではなく、ほかのツールの権限は別に設定・確認する必要があります。

今回できるのは、保存した解析範囲の中から、次に読むファイルの候補と根拠を返すことです。Tauriのすべての呼び出し形式、引数・戻り値の型、実行時の正しさ、現在のPR同士の衝突や安全なmergeを判定するものではありません。

解析器へAPIを付けるときは、入力と出力、対象の時点、分からない場合の表現も一緒に切り出す。その境界を再実行できる形で残しました。

## 次の実務実証を一つに絞る

次に検証する問いも、「コマンド改名で確認すべき接点を、AIが漏らさず確認できるか」に絞ります。複数PR予測、DBスキーマ変更、潜在バグ探索を一度に新機能として増やす段階ではありません。

最小の実務実証では、同じ固定repo・同じ問い・同じmodelと利用可能なsource・同じ作業予算を用意し、通常AIとCore併用を複数回比べます。出力前に定義・呼び出し・登録・権限の確認リストを作り、不明点を「安全」と断定しないかも評価します。機械時間だけでなく、人の修正確認、生成物の再生成、ビルド・テストまで進めた結果を別に測る必要があります。

今回の5確認先には、現在のMCPが返さない4ファイルがあります。まずここを含む確認作業が再現できるかを検証し、Core併用で見落としや根拠のない断定が減り、確認負担が増えすぎないかを見るのが次の課題です。成功すれば、PRイベントで同じ確認機会を作るAppの価値も検討できます。現時点では障害削減、導入効果、支払い意思は未確認です。

[GitとPythonだけのCoreローカルデモ](https://github.com/RollNuts/veripsa/tree/main/examples/structural-overlap)と、[Flaskの実変更を使う確認先調査](https://github.com/RollNuts/zenn-content/tree/main/examples/core-change-review)も公開しています。問いと限界はそれぞれ異なります。作者は[RollNuts](https://github.com/RollNuts)です。

本稿と再現コードの作成には、コーディングエージェントを利用しています。
