# Zenn記事の原稿 / Technical writing

Git・Python・RSS・静的サイトの実装と運用を扱う、日本語技術記事の原稿置き場です。

現在、**Zenn公開記事2本**を管理しています。

新着記事は[RSSでも購読できます](https://zenn.dev/veripsa/feed)。

## 公開記事

| テーマ | Zenn | 原稿 |
| --- | --- | --- |
| GitHubのブランチ整理 | [git branch --mergedに出ない取り込み済みブランチを見分ける――556本を整理した実例](https://zenn.dev/veripsa/articles/github-branch-cleanup-squash-556) | [Markdown](articles/github-branch-cleanup-squash-556.md) |
| 静的サイトの日時とRSS | [創作上の2031年をRSSに流さない――静的サイトで3つの日時を分ける](https://zenn.dev/veripsa/articles/fiction-date-rss-static-site) | [Markdown](articles/fiction-date-rss-static-site.md) |

## 再現コード

[ast-grep outlineの小さい再現例](examples/ast-grep-outline/README.md)は、TypeScript 3ファイルと7条件の実CLI検証をまとめています。ファイル・ディレクトリの表示や、出力に残る情報を確認できます。

[配信中のrevisionをHTTP応答で確認する最小例](examples/deployment-revision/README.md)は、Python 3.12の標準ライブラリだけで動きます。旧版・一部だけ更新・正常な配信の違いをローカルHTTPで試せます。

## 公開待ちの原稿

[ast-grep outlineでコードの目次を作る](articles/ast-grep-outline-code-map.md)は、再現コードの検証が済んだ原稿です。Zennの投稿数制限により未公開で、公開設定を下書きにして保管しています。

## ファイルの読み方

`articles/` のMarkdownが原稿です。先頭のfront matterにタイトル、トピック、公開設定があります。

公開リポジトリ内の原稿は誰でも閲覧できます。個人情報や認証情報、未許諾の引用・画像は追加しないでください。

## 利用について

このリポジトリでは再利用ライセンスを設定していません。転載・改変・再配布の条件は、事前に著者へ確認してください。
