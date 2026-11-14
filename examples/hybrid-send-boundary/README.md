# 変更の意味を隠すと、どのテストが必要か見分けられるか

公開用に作った二つの変更を、同じ呼び出し元で試します。変更前の関数は数を返し、引数を省略できます。Aでは引数を必須にし、Bでは戻り値を文字列にします。

Python 3.12の標準ライブラリだけで実行できます。リポジトリのルートで次を実行してください。

```sh
python3.12 -B examples/hybrid-send-boundary/compare.py
```

手元では、定義があるファイルを `F01`、呼び出し元を `F02` と呼びます。二つのテストはどちらも同じファイルから同じ定義を呼ぶので、ファイル間の関係は1件です。冒頭に出る対応表とテスト結果はローカル表示です。

```text
Local lookup: {"F01": "contracts.py", "F02": "compare.py"}
Local checks before: omit_argument=ok, add_one_to_result=ok
Local checks A: omit_argument=TypeError, add_one_to_result=ok
Local checks B: omit_argument=ok, add_one_to_result=TypeError
```

残りの出力では、仮に外へ出す候補として作ったJSONを比べます。件数だけでも呼び出し方向を加えても、AとBを見分ける値がありません。許可されたと仮定して筆者が付けた契約のメモまで加えると、どちらの検査を優先するか判断する材料が初めて現れます。

```text
withheld | A == B: True
  A: null
  B: null

count | A == B: True
  A: {"relations": 1}
  B: {"relations": 1}

relation | A == B: True
  A: {"caller": "F02", "definition": "F01"}
  B: {"caller": "F02", "definition": "F01"}

contract | A == B: False
  A: {"caller": "F02", "change": "optional_argument_becomes_required", "definition": "F01"}
  B: {"caller": "F02", "change": "number_result_becomes_text", "definition": "F01"}
```

`null` は候補なしの表示です。全ケースでJSONを端末に表示するだけです。実ファイル名、関数名、本文、テスト結果は候補へ入れません。モデルの精度・仮名化の安全性や実際の送信制御を測るには、別途検証が必要です。
