---
title: "Gitでマージ成功、それでも壊れる。ハイブリッドLLMに「一緒に検査する変更」を選ばせる構想"
emoji: "🧩"
type: "tech"
topics: ["git", "llm", "codereview", "testing", "localai"]
published: false
---

> 「私の考えるハイブリッドLLM～実践と構想～」構想部門向け。Surface Laptop Ultraと高性能GPU PCは所有していません。以下の合成コードの再現と、ローカル／クラウドLLMを組み合わせる未実装の設計は明確に分けます。

## Gitの成功は、アプリケーションの成功ではない

二つのブランチでそれぞれテストが通った。Gitでマージしてもコンフリクトは起きなかった。それなのに、統合後の実行で `TypeError` が出る。変更の調整で本当に知りたいのは、テキストが衝突するかではなく、**どの変更を一緒に検査すべきか**だ。

私は頻繁なGitコンフリクトを減らしたくてCoreを作り始め、その過程でコード構造の関係やGitの共変更履歴を扱うようになった。ここで紹介する4例は実運用の障害報告ではなく、公開された**合成ケース**である。構想は、既存の決定的な関係抽出をローカルLLMが整理し、難しい組合せだけクラウドLLMへ相談し、最終判定は統合テストに戻す仕組みだ。

```text
二つのPRと固定ベース
       ↓
構造グラフ + Git共変更履歴
       ↓
ローカルLLM: 関係候補・理由・不足情報を整理
       ├─ 明確な候補 → ローカル統合テストへ
       └─ 曖昧な候補 → 最小化した根拠をクラウドLLMへ
                                ↓
                        検査順の提案
                                ↓
                      統合テストで合否確定
```

モデルが「安全」と回答してもマージ可とはしない。モデルは**検査の優先順位を提案する**だけで、統合結果の判定器ではない。

## 固定コードで確認できた4ケース

[Coreの固定commit](https://github.com/RollNuts/veripsa/tree/2c6850617bacaaa5cd31e34a490983597a18086d) と [structural-overlapのREADME](https://github.com/RollNuts/veripsa/blob/2c6850617bacaaa5cd31e34a490983597a18086d/examples/structural-overlap/README.md)、[demo.py](https://github.com/RollNuts/veripsa/blob/2c6850617bacaaa5cd31e34a490983597a18086d/examples/structural-overlap/demo.py) が再現の土台である。固定版を取得して次のように実行する。

```sh
git clone https://github.com/RollNuts/veripsa.git
cd veripsa
git checkout 2c6850617bacaaa5cd31e34a490983597a18086d
python3.12 -B examples/structural-overlap/demo.py --git "$(command -v git)"
```

このコマンドは引継ぎ側で再実行され、終了コード0だった。私が今回改めて実行したものではない。4例とも**各ブランチ単独では成功し、Gitのマージはclean**。それでも統合実行には違いがあった。

| 合成ケース | 統合結果 | 注意する点 |
| --- | --- | --- |
| function_contract | `TypeError` | 関数の呼び出し契約がずれる |
| dynamic_lookup | `TypeError` | 動的参照が静的な確認を難しくする |
| compatible_related | 成功 | 関係があっても壊れるとは限らない |
| unrelated | 成功 | 共変更履歴があっても現在の依存とは限らない |

構造の候補と共変更履歴の**unionは4例を拾い**、intersectionは壊れる2例を両方落とした。unionなら候補が多くなる一方、intersectionで絞ると重大な候補を落とす可能性がある。関係警告は障害の確定ではないし、Co-changeは相関であって因果ではない。

この4例から「実際の障害を何％防いだ」とは言えない。LLMを使った比較実験でもない。確かめたのは、**テキスト上のclean mergeと、統合後の実行結果が一致しない場合がある**という限定的な事実だ。

## ローカルとクラウドをどう分担するか

ローカルモデルの候補は [gpt-oss-20b](https://developers.openai.com/api/docs/models/gpt-oss-20b)。open-weightでテキスト入力を扱えるため、端末内で候補を短く整理する役に置く。ただし実機での速度、メモリ、互換性、温度・電力は未検証で、実行環境もまだない。

ローカルLLMには、各PRが触れたシンボル、構造関係、共変更の観測、未解決の動的参照を一覧化させる。候補ごとに「なぜ同時に検査するのか」と「その理由を支える入力行」を返させる。候補を消す権限は与えない。特に `dynamic_lookup` のように静的関係が薄い場合は、推論だけで「無関係」としない。

クラウド側の候補は、複雑なコード推論を扱う [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)。ローカルの整理だけでは説明できない組合せについて、追加のテスト案を提案させる。クラウドへ送る情報は許可された最小の合成・抽象化データに限り、コード本文や内部パスを自動で送らない。APIの利用には従量課金が生じ得るので、今回の構想段階では呼び出さない。

返すものは「合格」「安全」ではなく、例えば次のような**検査計画**にする。

```json
{
  "pair": ["PR-A", "PR-B"],
  "reason": "caller/callee contract may diverge",
  "evidence": ["structure:call_edge", "history:cochange"],
  "proposed_checks": ["merge", "integration_test"],
  "confidence": "unverified"
}
```

これは実際のモデル出力ではなく設計例だ。実装時は提案が存在しなくても、決定的な統合テストの実行を省かない。モデルが不調なら保留し、テストへ戻す。

## cloud-only、local-onlyと公平に比べる

cloud-onlyならコードを一括で扱いやすいが、入力の外部送信とクラウドの呼び出し費用を検討する必要がある。local-onlyなら外部送信を抑えられるが、端末の処理能力やモデル品質に制約がある。hybridは難しい案件だけクラウドへ渡せる可能性がある一方、分類の誤り、送信審査、モデル間の引継ぎ、二重の保守が増える。

さらに、**LLMなしで構造解析＋テストだけを行う案**も強い比較対象だ。単に4ケースを正しく検査するだけなら、その方が単純かもしれない。LLMの価値は、統合テストの代わりではなく、検査対象が増えたときに人が判断する順序を支援できるかで測るべきだ。

## 実機が手に入ったら何を測るか

OS、ランタイム、モデルの版と量子化、端末の温度、入力の固定版を先に記録する。合成4例を含む、正解が統合実行で確かめられる追加ケースを用意する。同一入力でcloud-only、local-only、hybrid、そして非LLMの基準方式を比較する。

測定するのは、壊れる組合せを候補から落とした件数、無関係な組合せの過剰警告、根拠の誤引用、検査計画を人が確認する時間、保留率、再試行数、クラウド入出力トークンだ。ローカルの電力や運用負担も含める。評価前に件数や削減率を作らない。

最低限の合格条件は、`function_contract` と `dynamic_lookup` の両方を**同時検査の対象から落とさず**、最終の `TypeError` を統合テストで検出すること。`compatible_related` と `unrelated` は警告が出ても障害確定とは書かない。モデルが根拠を捏造したら失敗として数える。現状の4例だけで汎化性能は主張しない。

私が欲しいのは「コンフリクトを必ず防ぐAI」ではない。**どの変更を一緒に試すべきかを、人が根拠付きで選べる仕組み**だ。ハイブリッドLLMがその判断時間を本当に減らすかどうかは、これからの実験で決める。

参考: [Microsoft × Zennコンテスト](https://zenn.dev/contests/zennfes-autumn-2026-microsoft) / [イベント](https://zenn.dev/events/zennfes-autumn-2026)。
