---
title: "コードを送らないだけでは足りない。ハイブリッドLLMの「送信境界」を設計する"
emoji: "🔐"
type: "tech"
topics: ["llm", "security", "mcp", "architecture", "localai"]
published: false
---

> Microsoft × Zenn「私の考えるハイブリッドLLM～実践と構想～」構想部門向けの設計案です。Surface Laptop Ultraや高性能GPU PCは所有しておらず、ローカルLLM・クラウドLLMの組合せは未実装・未計測です。

## 「本文は送っていない」なら安全なのか

AIにコード変更の影響を尋ねたい。しかし、社内のソースコードをそのまま外部に送れるとは限らない。ではコード本文を消して、ファイル間の関係だけをクラウドへ送ればよいのだろうか。

私が提案したいのは、**どのモデルに何を考えさせるかより前に、どの情報を端末外へ出してよいかを決める**ハイブリッドLLMだ。ファイル名、コマンド名、依存関係の組合せだけでも内部構成を推測できる。モデルに「匿名化した？」と尋ねて「はい」と返っても、それを許可判定には使えない。

構想の経路は次のようになる。

```text
ローカルのコード / 固定snapshot
        ↓
既存の読み取り専用問い合わせ
        ↓
ローカルLLM: 質問の整理・根拠候補の要約
        ↓
決定的な送信ゲート: schema / 許可フィールド / 値 / サイズ
       ├─ 不許可 → 端末内に保持・理由を表示
       └─ 許可 → 最小JSONだけをクラウドLLMへ
                         ↓
                  解釈・追加質問案
                         ↓
                ローカルで根拠照合
```

ここで重要なのは、ゲートをLLMの自己申告から独立させること。ローカルモデルの判断は**候補**であり、送信許可ではない。

## すでに確かめた土台

出発点は、公開しているCoreの固定snapshotをローカルMCPで照会する実験だ。[固定版の再現手順](https://github.com/RollNuts/zenn-content/blob/6c3ef33ab0074ab7895602c46994e98c3d186bca/examples/core-local-mcp/README.md)と[query_service.py](https://github.com/RollNuts/zenn-content/blob/6c3ef33ab0074ab7895602c46994e98c3d186bca/examples/core-local-mcp/query_service.py)を公開している。

固定snapshotを読み取る2ツールがあり、入力は5MiB、表示は最大20行、JSONは32KiBまでという境界を設けている。標準ライブラリの `SnapshotQueries` で、同梱された4つのTauriケースの `src/client.ts` を照会した記録では、次の違いが出た。

| ケース | 結果 | 解釈 |
| --- | --- | --- |
| official-literal | observed / 1行 | 対象の関係を観測 |
| local-invoke | not_observed / 0行 | 対象範囲では観測されない |
| dynamic-name | not_observed / 0行 | 動的な名前解決を証明しない |
| duplicate-command | uncertain / 2行 | 曖昧・不完全な候補 |

`not_observed` は「安全」の意味ではない。`uncertain` は推論で補って確定させない。さらに `current_worktree_verified=false`、`current_state_or_merge_safety_proven=false` であり、今の作業ツリーやマージの安全性を検証したわけではない。

本文を省いても、関係JSONには `src-tauri/commands.rs` や `tauri_command::receipt_label` のような識別子が残る。つまり**本文を送らない仕組み**と**情報を外に出してよい仕組み**は別物だ。これらの観測は固定snapshotに対するもので、今回SDK通信やLLM推論を再実行した結果ではない。

CoreはGitコンフリクトを減らしたいという動機から作り始め、コードグラフや共変更履歴の機能が生まれた。CoreはBSL 1.1のsource-availableで、OSIの意味でのOSSではない。ホスト型GitHub Appは2026年8月18日から停止中。Appのイベント駆動処理とMCPのオンデマンド問い合わせは別の入口であり、どちらもモデルそのものではない。

## 構想する役割分担

ローカル候補には、テキストを扱えるopen-weightモデル [gpt-oss-20b](https://developers.openai.com/api/docs/models/gpt-oss-20b) を置く。候補を選ぶ理由は、手元の情報をまず端末内で解釈する実験ができるためだ。ただし、対象端末で動くこと、速度、必要メモリ、電池消費は未確認である。モデルをダウンロードしたわけでもない。

ローカル側にさせるのは「この問い合わせは何を知りたいのか」「どの観測行が根拠か」「どこが未観測か」を整理すること。許可のない情報はここで止める。クラウド候補の [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) は、許可済みの最小情報について、複雑な関係の解釈や見落とし候補を提案する役割とする。API利用には別途課金が生じ得るため、今回は呼び出さない。

例えばクラウドへ渡す形式は次のように限定する構想だ。

```json
{
  "question_type": "change_impact",
  "observations": [
    {"relation": "calls", "status": "uncertain", "count": 2}
  ],
  "unknowns": ["dynamic_resolution"]
}
```

これは**送信形式の設計例であり、実際に送信したログではない**。実システムでは自由文・元パス・生の識別子を許さず、許可フィールドの型と列挙値、件数、サイズ、相互の組合せまで検査する。JSONに埋めた値から機密が漏れる可能性も残るため、機密区分の人手による確認と監査可能な拒否理由を設ける。出力をそのままコード変更に反映しない。

## 選ばない案も比較する

| 方式 | 利点 | 見落としやすい点 |
| --- | --- | --- |
| cloud-only | 強い推論へ一括して渡せる | 入力の外部送信境界が広がる |
| local-only | 外部送信を避けやすい | モデル品質・端末負荷・保守を端末側で負う |
| 提案するhybrid | 端末内の整理と限定的な外部推論を分離 | ゲートの設計・運用が増え、誤送信の可能性は消えない |

安全性が最優先なら、クラウドへ何も送らない `local-only` や、そもそもLLMを使わない検索の方が適切な場面もある。ハイブリッド化は目的ではない。

## 実機入手後の最小実験

最初にOS、ランタイム、モデルの固定版・量子化、温度条件、入力snapshotを記録する。同じ質問セットをcloud-only、local-only、hybridで比較する。合成の秘密マーカーをファイル名・識別子・自由文に埋め、ゲート前後のデータを機械的に比較する。**秘密マーカー検査はまだ実施していない。**

合格条件は、許可されないフィールドと秘密マーカーが送信ログに一切現れず、ゲートが拒否した入力ではクラウド呼び出しが発生しないこと。根拠行の取り違え、`not_observed` を「安全」と言い換える誤りも失敗と数える。誤送信率だけでなく、人の確認時間、保留率、再試行数、クラウド入出力トークン、ローカルの端末・電力・保守負担も記録する。結果が出るまでは削減率を語らない。

最も怖い失敗は「ローカルで処理したから安全」という思い込みだ。境界が検証できなければクラウドへの経路を閉じる。私が考えるハイブリッドLLMの価値は、モデルを二つ並べることではなく、**外へ出せる情報を検査可能な仕様として扱うこと**にある。

参考: [コンテスト](https://zenn.dev/contests/zennfes-autumn-2026-microsoft) / [イベント](https://zenn.dev/events/zennfes-autumn-2026) / [Surface向け参考kit](https://github.com/dahatake/Surface-Laptop-Ultra-RTX-Spark-Vibe-Coding-kit)（性能の実証としては使用しない）。
