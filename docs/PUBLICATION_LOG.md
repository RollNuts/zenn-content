# 公開記録と次回の候補

## 状態の区別

- 公開待ち: 原稿があり、Zennへの公開は未実施。
- GitHub反映済み・Zenn未確認: 公開設定を反映したが、公開URLの本文確認がまだ済んでいない。
- Zenn公開確認済み: 公開URLに目的の記事本文が表示されていることを確認した。

READMEの公開本数には「Zenn公開確認済み」だけを数える。

## 直近の公開

| 項目 | 記録 |
| --- | --- |
| slug | `ast-grep-outline-code-map` |
| 記事 | AIに全文を渡す前に、ast-grep outlineでコードの目次を作る |
| 状態 | Zenn公開確認済み |
| 公開URL | https://zenn.dev/veripsa/articles/ast-grep-outline-code-map |
| 反映commit | [`22d53574bd766ae922a9ceb1a25101d4a9235c0c`](https://github.com/RollNuts/zenn-content/commit/22d53574bd766ae922a9ceb1a25101d4a9235c0c) |
| 公開確認 | 2026年11月12日 23:59 JST、公開ブラウザーで本文を確認 |
| Zenn上の公開日表示 | 2026/11/12 |
| 本文の照合 | タイトル、Linux/Python 3.12.14の再検証記載、固定commitを使う取得手順、ファイル表示順の補足、7条件の一覧が一致 |
| 検証 | ast-grep 0.51.1 / Python 3.12.14 / Linux、既存`verify.py`の7条件PASS、終了コード0 |
| サンプルの固定 | `11e8c3ae649d2775497b9e2dd6de75be9258fd12` のfixtureと検証スクリプトが実行対象と一致 |
| 公開前の改善 | 再現コードの取得・作業場所を明示、ディレクトリの表示順を補足、導入文を整理 |
| 未完了 | なし |

公開表示とGitHub反映を確認した後、公開一覧を5本から6本へ更新した。

## 次回の候補

| 優先 | 原稿 | 状態 | 次に行うこと |
| --- | --- | --- | --- |
| 1 | [`webhook-commit-response-lost`](../articles/webhook-commit-response-lost.md) | 公開待ち・`published: false` | 固定Coreのfakeテストと本文の3分岐・4チェックを再照合。実DBやexactly-onceの証明と混同していないことを確認後、投稿条件が整った回に公開 |
| 2 | [`api-contract-repair-review`](../articles/api-contract-repair-review.md) | 公開前レビュー待ち・`published: false` | 標準ライブラリの実習を再実行し、既存記事との重複・読者の疑問・期待結果を確認 |

新しい公開候補を決める前に、公開済み記事の不具合や前回の公開未確認があれば先に対応する。
