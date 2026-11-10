# Zenn記事の原稿 / Technical writing

Git・Python・RSS・静的サイト・コード解析の実装と運用を扱う、日本語技術記事の原稿置き場です。

現在、**Zenn公開記事5本**を管理しています。

新着記事は[RSSでも購読できます](https://zenn.dev/veripsa/feed)。

## 公開記事

| テーマ | Zenn | 原稿 |
| --- | --- | --- |
| CI/CDの公開確認 | [CIは成功したのに本番が変わらないとき、どこを確かめるか](https://zenn.dev/veripsa/articles/ci-success-deployed-revision) | [Markdown](articles/ci-success-deployed-revision.md) |
| コードグラフとCo-changeの検証 | [Gitでマージできたのに壊れる――コードグラフとCo-changeを4例で検証](https://zenn.dev/veripsa/articles/graph-cochange-review-benchmark) | [Markdown](articles/graph-cochange-review-benchmark.md) |
| CoreのMCP連携 | [Tauriコマンドの変更影響をAIは追える？Codex・MCP・検索を比較](https://zenn.dev/veripsa/articles/tauri-command-contract-graph) | [Markdown](articles/tauri-command-contract-graph.md) |
| GitHubのブランチ整理 | [git branch --mergedに出ない取り込み済みブランチを見分ける――556本を整理した実例](https://zenn.dev/veripsa/articles/github-branch-cleanup-squash-556) | [Markdown](articles/github-branch-cleanup-squash-556.md) |
| 静的サイトの日時とRSS | [創作上の2031年をRSSに流さない――静的サイトで3つの日時を分ける](https://zenn.dev/veripsa/articles/fiction-date-rss-static-site) | [Markdown](articles/fiction-date-rss-static-site.md) |

## 再現コード

[公開済みRails修正をCoreの監査索引で比べる例](examples/rails-known-fix-review/README.md)は、Chatwootの固定した修正前後をローカルで解析します。固定したCoreの監査索引v1で観測した未解決のRails scopeと、安全性を判定できない限界を記録し、後続の起動契約・route索引の改善は別に案内します。

[Flaskの実変更の前に確認先を探すケース調査](examples/core-change-review/README.md)は、変更直前のコードグラフとGit履歴を比較します。事前に選んだ5確認先の包含と、候補総数を分けて確認できます。モデル・DB・追加パッケージは不要です。

[Coreの契約グラフをローカルMCPで照会する実験](examples/core-local-mcp/README.md)は、本文を省いたsnapshotを2ツールから読みます。公式SDKの新旧初期化方式と、Codex CLIからの実ツール呼び出しを確認するコード・記録を含みます。

[ブランチ整理の候補条件を試す10件のテスト](examples/branch-cleanup-candidates/README.md)は、公開記事の関数を架空のPR・ブランチ情報で検証します。Python 3.12の標準ライブラリだけで実行できます。

[CoreでTauriの文字列契約をグラフにする再現例](examples/tauri-command-contract/README.md)は、固定した公開CoreでRustとTypeScriptの4ケースを検証します。公式呼び出し・同名の自作関数・変数による名前・重複定義を比較できます。

[ast-grep outlineの小さい再現例](examples/ast-grep-outline/README.md)は、TypeScript 3ファイルと7条件の実CLI検証をまとめています。ファイル・ディレクトリの表示や、出力に残る情報を確認できます。

[配信中のrevisionをHTTP応答で確認する最小例](examples/deployment-revision/README.md)は、Python 3.12の標準ライブラリだけで動きます。旧版・一部だけ更新・正常な配信の違いをローカルHTTPで試せます。

## 公開待ちの原稿

[ast-grep outlineでコードの目次を作る](articles/ast-grep-outline-code-map.md)は、再現コードの検証が済んだ原稿です。Zennの投稿数制限により未公開で、公開設定を下書きにして保管しています。

[Webhookを再試行してよい？COMMITの応答が消えたときの3つの分岐](articles/webhook-commit-response-lost.md)は、公開Coreのfake接続テストを使った、完成・検証済みの無料技術解説です。呼び出し側の3分岐と4チェックを扱い、実DBやexactly-onceの証明とは区別しています。ast-grep稿に続く2番目の公開候補として、`published: false`で保管しています。この原稿のZenn公開はまだ試していません。

## ファイルの読み方

`articles/` のMarkdownが原稿です。先頭のfront matterにタイトル、トピック、公開設定があります。

公開リポジトリ内の原稿は誰でも閲覧できます。個人情報や認証情報、未許諾の引用・画像は追加しないでください。

## 利用について

このリポジトリでは再利用ライセンスを設定していません。転載・改変・再配布の条件は、事前に著者へ確認してください。
