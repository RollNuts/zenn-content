---
title: "RustとTypeScriptをつなぐTauriの文字列契約を、4つの例で調べる"
emoji: "🔗"
type: "tech"
topics: ["tauri", "rust", "typescript", "静的解析", "個人開発"]
published: false
---

Rustのコマンド名を変えたとき、フロント側のどこを見直すべきか。

Tauriでは、TypeScriptから`invoke('receipt_label')`のように名前を指定してRustの処理を呼べます。この関係は、RustファイルとTypeScriptファイルの間の`import`だけを追っても表れません。

個人開発していたVeripsa Coreには、このような言語をまたぐ関係をグラフへ加える実装があります。今回は公開ソースを固定し、小さい入力で**関係を抽出する・抽出しない・曖昧さを残す**という違いを確かめました。

対象は[公開Coreのcommit `d22d44f`](https://github.com/RollNuts/veripsa/tree/d22d44f12112784d34d5ea7ba20755ca995adad2)です。再現例は解析用のコード断片で、Tauriアプリのビルドは行いません。Coreのホスト版は停止中で、この記事はローカルの抽出器を扱います。

## ファイル同士の間に、コマンドを置く

Rust側に、次の宣言があるとします。

```rust
#[tauri::command]
pub fn receipt_label(count: u32) -> String {
    format!("FIXTURE_BODY_TEXT_SHOULD_STAY_OUT_OF_GRAPH: {count}")
}
```

TypeScript側からは公式APIを使い、同じ名前を指定します。

```ts
import { invoke } from "@tauri-apps/api/core";

export async function requestLabel() {
  return invoke("receipt_label", { count: 3 });
}
```

Tauriの実際のアプリでは、Rustコマンドを`invoke_handler`へ登録する工程も必要です。[公式ガイド](https://v2.tauri.app/develop/calling-rust/#basic-example)に宣言・登録・呼び出しの流れがあります。今回の抽出器は、その登録表までは検証しません。

この断片からCoreが作るのは、次の形の関係です。

```text
Rustのファイル ──alters──▶ tauri_command::receipt_label
TSのファイル   ──queries─▶ tauri_command::receipt_label
```

`tauri_command::receipt_label`は、種類が`app_command`の共通ノードです。ファイル間に直接の`import`を作る代わりに、同じ契約名へ辺を張ります。

ここでの`alters`と`queries`はCoreのグラフ上の役割名です。コマンドの副作用や、読み取り専用かどうかを解析した結果ではありません。

## 4つの入力を比べる

正例だけでは、何を根拠に結んだのか分かりにくいため、呼び出し方と定義の数を変えます。

| 入力 | TS側のTauri参照辺 | 注目する点 |
| --- | --- | --- |
| 公式APIからimportし、既知の名前をリテラルで呼ぶ | できる | 定義側と同じ契約へ結ぶ |
| 自前の同名関数`invoke`を呼ぶ | できない | 関数名だけでは結ばない |
| 公式APIを使い、名前を変数で渡す | できない | この抽出規則は値を追跡しない |
| 別のRustファイルにも同名コマンドを定義する | `ambiguous`として残る | 勝手に定義先を1つに決めない |

### 同名の関数を拾わない

次の`invoke`は自前の関数です。

```ts
function invoke(command: string) {
  return command;
}

export function requestLabel() {
  return invoke("receipt_label");
}
```

今回の規則では、公式APIモジュールからのimportがないため、TS側のTauri参照辺は作りません。Rustの宣言に対応するノードと辺は残ります。

この対照から確認できるのは、「公式importのない、この形の同名関数を拾わなかった」ことです。すべてのスコープや同名関数を解決できた、という意味には広げられません。

### 変数の値を推測しない

```ts
import { invoke } from "@tauri-apps/api/core";

const command = "receipt_label";

export async function requestLabel() {
  return invoke(command, { count: 3 });
}
```

人間には名前が分かる小さい例ですが、この抽出器は定数伝播をしません。リテラルを直接渡していないので、TS側のTauri参照辺は作られません。

Tauri API自体の`cmd`の型は`string`です。変数での呼び出しをTauriが禁止しているわけではありません。[公式API](https://v2.tauri.app/reference/javascript/api/namespacecore/#invoke)

つまり、**辺が出なかったことを「依存がない」と読み替えられません。** 今回は解析規則の外にある呼び出し方です。

### 重複した定義を、曖昧なまま残す

2つのRustファイルに`#[tauri::command] fn receipt_label`を置くと、名前だけでは呼び先を1つに決められません。

固定した実装は、共通ノードの`provenance`に`ambiguous: true`を付け、両方の定義辺とTS側の参照辺を`reference_status: "ambiguous"`として残します。関係するファイルの`analysis_status`も`ambiguous`になります。

これは抽出器の対照実験です。この2重定義を、そのまま実行可能なTauriアプリの構成として扱ってはいません。

曖昧な証拠を捨てずに残すと、「何もなかった」のか、「候補はあるが確定できなかった」のかを、後段で分けて扱えます。

## 手元で同じ結果を確かめる

[再現コード](https://github.com/RollNuts/zenn-content/tree/6fd51b7af7d408a0238e8d24b5d9513cae1298b5/examples/tauri-command-contract)には4つの入力と検証スクリプトをまとめています。解析対象は同梱した架空の断片だけです。エンジンは同梱せず、固定したCoreのチェックアウトを渡します。

Python 3.12とGitを使います。検証した環境はmacOSで、パーサーは次の版です。

```text
tree-sitter             0.23.2
tree-sitter-javascript  0.23.1
tree-sitter-typescript  0.23.2
tree-sitter-rust        0.21.2
PyYAML                  6.0.3
```

Coreの[依存定義](https://github.com/RollNuts/veripsa/blob/d22d44f12112784d34d5ea7ba20755ca995adad2/requirements.txt)には、tree-sitter本体とgrammarのABIを合わせるための制約があります。この実験ではRust・TypeScriptに必要な範囲だけを揃えます。

実行手順は再現コードのREADMEに記載しています。検証スクリプトは固定Coreの確認、必要なパーサーの確認、4つのケースの期待結果の照合を行います。観測した契約辺とファイルの状態をJSONへ保存し、中間結果も読めるようにしています。

実際の結果は次のとおりでした。`null`は状態マーカーが付かなかったことを表します。

| ケース | `alters` | `queries` | 辺の`reference_status` | ファイルの`analysis_status` |
| --- | ---: | ---: | --- | --- |
| official-literal | 1 | 1 | null ×2 | null ×2 |
| local-invoke | 1 | 0 | null ×1 | null ×2 |
| dynamic-name | 1 | 0 | null ×1 | null ×2 |
| duplicate-command | 2 | 1 | ambiguous ×3 | ambiguous ×3 |

4ケースとも`app_command`ノードは1個でした。動的名のケースは、未解決の辺を作っているわけでもありません。またRustの説明用文字列が返却グラフへ混ざらないことを、この入力について確認しています。

## この関係を何に使うか

Rust側の変更時に、同じ契約へつながったフロント側のファイルを調査候補として出せれば、レビューで読む入口になります。

ただし、今回のTauri抽出規則は正規表現による限定したものです。登録の有無、引数と戻り値の型、権限、ラッパー経由の呼び出し、すべての公式呼び出し形式を網羅する検査にはなっていません。グラフが得られても、実行時の正しさやPRの安全な取り込みを保証しません。

実装を読み直して残したいと思ったのは、共通ノードへ結ぶ方法に加えて、**どの入力では結ばないか、どの入力では確定しないかを、再実行できる例にすること**でした。自分の開発で作った解析規則も、入力・出力・限界を並べると、ほかの人が試せる技術資産になります。

抽出規則は[`_cg_tauri.py`](https://github.com/RollNuts/veripsa/blob/d22d44f12112784d34d5ea7ba20755ca995adad2/_cg_tauri.py)、元のテストは[`test_tauri_command_contract.py`](https://github.com/RollNuts/veripsa/blob/d22d44f12112784d34d5ea7ba20755ca995adad2/tests/test_tauri_command_contract.py)で読めます。Coreは[Business Source License 1.1](https://github.com/RollNuts/veripsa/blob/d22d44f12112784d34d5ea7ba20755ca995adad2/LICENSE)で公開されているsource-availableのソフトウェアです。
