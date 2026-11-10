# Zenn記事の原稿 / Technical writing

Git・Python・RSS・静的サイト・コード解析の実装と運用を扱う、日本語技術記事の原稿置き場です。

現在、**Zenn公開記事4本**を管理しています。

新着記事は[RSSでも購読できます](https://zenn.dev/veripsa/feed)。

## 困りごとから試す

RollNutsが、実装と検証の過程を記事・実行コードとして残しています。
初めての方は、追加パッケージなしで動くPythonの小さい例から試せます。

| 確かめたいこと | 実行例 | 分かること・範囲 |
| --- | --- | --- |
| テストが通る二つの修正を、どう選ぶか | [API契約を照合する実習](examples/api-contract-repair/README.md) | 同じ値を返しても、引数の渡し方に関する要求を守るかが違う。架空の関数・要求を使う教材 |
| HTTP 200なのに公開内容が古いとき、何を比較するか | [配信中のrevisionを確認する例](examples/deployment-revision/README.md) | 旧版・一部だけ更新・正常な配信をローカルHTTPで比較。全ページやブラウザ操作の検査は対象外 |
| 変更前に関連ファイルの候補をどう探すか | [Flaskの実変更を使うCore CLI調査](examples/core-change-review/README.md) | 静的グラフとGit履歴の候補を比較。固定Core・対象repoの取得が必要で、変更の安全性は判定しない |

最初のAPI契約の実習は、リンク先の`repair_review.py`を保存し、Python 3.12で実行できます。
実行時のCore・モデル・アカウント・ネットワーク接続は不要です。

```sh
python3.12 repair_review.py --repair rollback --value-only
python3.12 repair_review.py --repair keyword --value-only
python3.12 repair_review.py --repair rollback
python3.12 repair_review.py --repair keyword
```

最初の2回は、どちらも値だけの1テストに成功します。
3回目は、教材で指定したAPI契約に反するため4テスト中2件が失敗し、終了コード1になります。
4回目は同じ4テストに成功します。架空の要求を変えれば、採用する修正の判断も変わります。
実際のAIによる修正や、一般的なバグ防止効果を測った実験ではありません。

## 公開記事

| テーマ | Zenn | 原稿 |
| --- | --- | --- |
| コードグラフとCo-changeの検証 | [Gitでマージできたのに壊れる――コードグラフとCo-changeを4例で検証](https://zenn.dev/veripsa/articles/graph-cochange-review-benchmark) | [Markdown](articles/graph-cochange-review-benchmark.md) |
| CoreのMCP連携 | [Tauriコマンドの変更影響をAIは追える？Codex・MCP・検索を比較](https://zenn.dev/veripsa/articles/tauri-command-contract-graph) | [Markdown](articles/tauri-command-contract-graph.md) |
| GitHubのブランチ整理 | [git branch --mergedに出ない取り込み済みブランチを見分ける――556本を整理した実例](https://zenn.dev/veripsa/articles/github-branch-cleanup-squash-556) | [Markdown](articles/github-branch-cleanup-squash-556.md) |
| 静的サイトの日時とRSS | [創作上の2031年をRSSに流さない――静的サイトで3つの日時を分ける](https://zenn.dev/veripsa/articles/fiction-date-rss-static-site) | [Markdown](articles/fiction-date-rss-static-site.md) |

## 再現コード

[実行が通る二つの修正を、要求と照合する実習](examples/repair-review/README.md)は、固定Coreの合成例を再利用し、同じ105を返す二案でもAPIの要求を守るかが異なることを確認します。未コミット変更による静的候補の変化と、共変更が増えてもliftが下がる履歴の対比も、既存CLIで再現します。追加パッケージ・モデル・DBは不要です。

[公開済みRails修正をCoreの監査索引で比べる例](examples/rails-known-fix-review/README.md)は、Chatwootの固定した修正前後をローカルで解析します。固定したCoreの監査索引v1で観測した未解決のRails scopeと、安全性を判定できない限界を記録し、後続の起動契約・route索引の改善は別に案内します。

[Flaskの実変更の前に確認先を探すケース調査](examples/core-change-review/README.md)は、変更直前のコードグラフとGit履歴を比較します。事前に選んだ5確認先の包含と、候補総数を分けて確認できます。モデル・DB・追加パッケージは不要です。

[Coreの契約グラフをローカルMCPで照会する実験](examples/core-local-mcp/README.md)は、本文を省いたsnapshotを2ツールから読みます。公式SDKの新旧初期化方式と、Codex CLIからの実ツール呼び出しを確認するコード・記録を含みます。

[ブランチ整理の候補条件を試す10件のテスト](examples/branch-cleanup-candidates/README.md)は、公開記事の関数を架空のPR・ブランチ情報で検証します。Python 3.12の標準ライブラリだけで実行できます。

[CoreでTauriの文字列契約をグラフにする再現例](examples/tauri-command-contract/README.md)は、固定した公開CoreでRustとTypeScriptの4ケースを検証します。公式呼び出し・同名の自作関数・変数による名前・重複定義を比較できます。

[ast-grep outlineの小さい再現例](examples/ast-grep-outline/README.md)は、TypeScript 3ファイルと7条件の実CLI検証をまとめています。ファイル・ディレクトリの表示や、出力に残る情報を確認できます。

[配信中のrevisionをHTTP応答で確認する最小例](examples/deployment-revision/README.md)は、Python 3.12の標準ライブラリだけで動きます。旧版・一部だけ更新・正常な配信の違いをローカルHTTPで試せます。

## 公開待ちの原稿

[CIは成功したのに本番が変わらないとき、どこを確かめるか](articles/ci-success-deployed-revision.md)は、一般的なWeb公開の切り分け方を3状態のローカル再現と公開ログで説明する完成稿です。Zennの投稿数上限により未公開で、次の公開対象として下書き設定で保存しています。

[ast-grep outlineでコードの目次を作る](articles/ast-grep-outline-code-map.md)は、再現コードの検証が済んだ原稿です。Zennの投稿数制限により未公開で、公開設定を下書きにして保管しています。

[Webhookを再試行してよい？COMMITの応答が消えたときの3つの分岐](articles/webhook-commit-response-lost.md)は、公開Coreのfake接続テストを使った、完成・検証済みの無料技術解説です。呼び出し側の3分岐と4チェックを扱い、実DBやexactly-onceの証明とは区別しています。上記2本に続く3番目の公開候補として、`published: false`で保管しています。この原稿のZenn公開はまだ試していません。

## ファイルの読み方

`articles/` のMarkdownが原稿です。先頭のfront matterにタイトル、トピック、公開設定があります。

公開リポジトリ内の原稿は誰でも閲覧できます。個人情報や認証情報、未許諾の引用・画像は追加しないでください。

## 利用について

このリポジトリでは再利用ライセンスを設定していません。転載・改変・再配布の条件は、事前に著者へ確認してください。
