# 修正を採る前のレビュー用メモ

変更の目的、確かめた結果、採否の理由を一緒に渡すためのメモです。必要な欄を使い、分からないことは「未確認」と書きます。実行していない検査は実行済みとして扱いません。記入しただけで修正の正しさを保証するものではありません。

## 記入例

以下は架空の教材 `repair_review.py` の追試結果です。実際にAIが提案した修正や、実サービスの採用判断の記録ではありません。

```text
対象の変更・版：
  repair_review.pyの二つの修正案
  a127a99bc240e13f981dbccaa1a1dd1fa7b4a552
今起きていること：
  feeをキーワード専用にした関数へ、古い呼び出しが位置引数を渡している
変更の目的：
  feeをキーワード専用にした状態でcheckout()を動かす
要求の根拠：
  この教材で明示した3条件（実サービスの合意済み仕様ではない）

採るための条件と確認方法：
  期待する結果：checkout() == 105
  許可する使い方：total(100, fee=5) == 105
  定義の条件：inspect.signatureでfeeがKEYWORD_ONLY
  拒否する使い方：total(100, 5)はTypeError

実行した環境・コマンド：
  Python 3.12.13、repair_review.pyを保存したディレクトリで実行
  python3.12 repair_review.py --repair rollback --value-only
  python3.12 repair_review.py --repair keyword --value-only
  python3.12 repair_review.py --repair rollback
  python3.12 repair_review.py --repair keyword
結果：
  値だけ：A、Bとも1件成功、終了コード0
  Aの全検査：4件中2件失敗、終了コード1
    test_fee_is_keyword_only
    test_positional_fee_is_rejected
  Bの全検査：4件成功、終了コード0
未確認と、採否への影響：
  ほかの呼び出し元、境界値の網羅、実サービスの移行要件は未確認
  実アプリへ適用する判断には、そのアプリの要求と追加確認が必要
判断と理由：
  教材の3条件ではBを採用
  Aは定義と拒否条件を満たさないため差し戻し
次に確認すること：
  実アプリで使うなら、古い位置引数の呼び出しを維持する必要があるか
```

## コピーして使う空欄

```text
対象の変更・版：
今起きていること：
変更の目的：
要求の根拠：

採るための条件と確認方法：
  期待する結果：
  許可する使い方：
  拒否する使い方：

実行した環境・コマンド：
結果：
未確認と、採否への影響：
判断と理由（採用／差し戻し／保留）：
次に確認すること：
```

要求の根拠には、合意済みの仕様、Issue、移行方針などを置きます。未コミットの変更がある場合は、commitだけでなく対象差分も残してください。テストを変えた場合は、変わる要求とその根拠も添えます。他人へ渡すメモには、公開できる情報だけを記載してください。

教材のコードは[固定版](https://github.com/RollNuts/zenn-content/blob/a127a99bc240e13f981dbccaa1a1dd1fa7b4a552/examples/api-contract-repair/repair_review.py)にあります。準備・実行検証にはAIを利用しています。
