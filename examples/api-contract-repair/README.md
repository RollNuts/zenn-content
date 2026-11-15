# どちらも105を返す。あなたなら、どちらの修正を採る？

会計処理の手数料をキーワードで渡すように変更したら、古い呼び出しが失敗しました。どちらの修正でも合計は105に戻ります。この問題の要求は「合計が105」「手数料はキーワード専用」「位置引数で手数料を渡したら拒否」の三つです。

| 案 | 修正 |
| --- | --- |
| A | 関数を `total(amount, fee=5)` に戻し、呼び出しを `total(100, 5)` のまま残す |
| B | 関数の `total(amount, *, fee=5)` を維持し、呼び出しを `total(100, fee=5)` に変える |

どちらを採用しますか。もう片方も値のテストには通る理由を考えてから、答えを開いてください。

<details>
<summary>答えと、もう一方が失敗するテスト</summary>

**この要求ならBです。** Aも100に5を足すので105を返しますが、位置引数を受け付けます。値だけのテストは両方とも1件成功。引数の渡し方まで含めると、4件のうちAはキーワード専用と位置引数拒否の2件で失敗し、Bは4件とも成功します。

逆に「既存の位置引数の呼び出しを動かし続ける」が要求だった場合は、Bをそのまま採用できません。採用理由を記録するときは、守ると決めた要求も一緒に書きます。

</details>

[Pythonファイル](repair_review.py)を保存すれば、下の4コマンドで答えを追試できます。問題と解答は無料です。[300円の自己採点式ワークブックについての読者アンケート](https://github.com/RollNuts/zenn-content/issues/42)も任意で受け付けています。

## Run the exercise

This synthetic Python exercise compares two repairs under three stated requirements:
`checkout()` returns 105, `fee` is keyword-only, and positional `fee` is rejected.
These are teaching requirements, not a real application's agreed specification.

Use Python 3.12 and save or download `repair_review.py` into an empty working directory.
No Git checkout, Core, model, account, network access, or additional package is needed
to run this file.

```sh
python3.12 repair_review.py --repair rollback --value-only
python3.12 repair_review.py --repair keyword --value-only
python3.12 repair_review.py --repair rollback
python3.12 repair_review.py --repair keyword
```

| Selection | Tests run | Failures | Exit code |
| --- | ---: | ---: | ---: |
| rollback, value-only | 1 | 0 | 0 |
| keyword, value-only | 1 | 0 | 0 |
| rollback, full | 4 | 2 | 1 |
| keyword, full | 4 | 0 | 0 |

The full rollback run is expected to fail: it accepts positional `fee`, breaking two
of the stated API requirements. Do not weaken these checks to turn it green. If the
actual requirement were to preserve positional callers, the desired API would differ.

From a repository checkout, run `python3.12 scripts/verify_api_contract_example.py`
to verify all four CLI results automatically. The verifier uses only the standard
library, resolves the example relative to its own file, and gives each run 10 seconds.
It requires the exact test names and statuses, test count, summary, and exit code;
the full rollback must fail only `test_fee_is_keyword_only` and
`test_positional_fee_is_rejected`. A syntax/import error or an unexpectedly passing
rollback fails verification. A read-only GitHub Actions workflow is included, but
Actions is disabled for this repository as of 2026-11-13, so the workflow has not run.
Use the standard-library command above for local verification. Exercise execution
needs no packages, network access, or secrets. This checks the documented exercise
behavior; article claims and teaching quality still need editorial review.

The checks cover these synthetic functions and inputs only. They do not establish
general correctness, merge safety, bug prevention, or any AI model's behavior.
The code and article were prepared with a coding agent.
