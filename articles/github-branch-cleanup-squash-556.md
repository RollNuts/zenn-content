---
title: "git branch --mergedに出ない取り込み済みブランチを見分ける――556本を整理した実例"
emoji: "🌿"
type: "tech"
topics: ["git", "github", "python", "個人開発"]
published: true
---

GitHubでPRを取り込んだはずなのに、作業ブランチが残っている。`git branch --merged main`を見ても、その枝が出てこない。

個人開発の公開リポジトリを整理したとき、リモートに556本のブランチがありました。PRの取り込み記録と現在のheadを照合し、453本を整理して103本を残しました。その候補453本のうち、保存時の`main`からGitの祖先関係で到達できたのは50本で、403本は`--merged`の一覧に入りませんでした。

この記事は、GitHubでsquash mergeやrebase mergeを使い、古いリモートブランチを整理したい人向けです。削除候補の見分け方、残した枝の理由、削除前の復元確認をまとめます。

## `--merged`が見ているもの

[Gitの公式説明](https://git-scm.com/docs/git-branch)では、`--merged`は指定コミットから到達できるtipを持つブランチを列挙します。PRの画面上の状態を問い合わせるコマンドではありません。

通常のcloneでリモート追跡ブランチを見る場合は、`git branch -r --merged origin/main`のように指定します。今回の50本／403本の比較は、削除前に保存したmirrorの`refs/heads`を、保存時のmainに対して調べたものです。

squash mergeでは、作業側の複数コミットがまとめられ、base側に新しいコミットができます。[GitHubのマージ方式の説明](https://docs.github.com/en/pull-requests/reference/pull-request-merges)も参照できます。

```text
A---B---S  main
     \
      C---D  feature

SにはC・Dをまとめた変更が入っていても、
DそのものがSの祖先になるとは限らない。
```

rebase mergeでもSHAが変わることがあります。「PRが取り込まれた」と「そのheadコミットがmainの祖先にある」は、別の確認になります。

先ほどの403本すべてをsquash mergeと分類したわけではありません。今回確認できたのは、**取り込み記録とhead SHAが一致した候補でも、祖先関係の一覧だけでは拾えない枝が多かった**という事実です。

## PRの取り込み記録と現在のheadを突き合わせる

候補にしたのは、次の条件を確認できた枝です。

- PRの`merged_at`があり、取り込み先が対象repoの`main`である。
- PRのheadが対象repoに属し、ブランチ名も一致している。
- 現在のブランチSHAが、取り込み済みPRのhead SHAと完全一致する。
- 取得した対象repoのPRで、その枝をheadまたはbaseに使う未完PRがなく、既定ブランチや保護対象ではない。
- 取り込みから24時間以上が経過している。

PRが閉じられただけでは、取り込まれたとは判断しません。また、マージ後に同じ枝へ新しいコミットがpushされていたら、古いPRの取り込み記録だけで候補へ入れません。

24時間という待機幅は、この作業で使った保守的な運用条件です。どのrepoにも当てはまる安全性の証明ではありません。

### 候補の照合部分をPythonで書くと

以下は、GitHub REST APIで取得したbranchesとPRsを、1件ずつの辞書のリストとして渡す例です。`repository`には`owner/name`、`default_branch`には既定ブランチ名、`cutoff`にはタイムゾーン付きの日時を渡します。

GitHub CLIで複数ページを保存する場合は、たとえば次のように取得します。これらは読み取りだけの操作です。

```sh
REPOSITORY="OWNER/REPO"
gh api "repos/$REPOSITORY/branches?per_page=100" --paginate --slurp > branches.json
gh api "repos/$REPOSITORY/pulls?state=all&per_page=100" --paginate --slurp > prs.json
```

`--slurp`の結果は「ページの配列」なので、読み込んだ後に1段平坦化します。

```python
import json
from datetime import datetime, timedelta, timezone

with open("branches.json") as f:
    branches = [item for page in json.load(f) for item in page]
with open("prs.json") as f:
    prs = [item for page in json.load(f) for item in page]

cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
```

照合する関数は次の形です。返すのはレビュー用の候補で、ブランチの削除は行いません。

```python
from datetime import datetime


def candidates(branches, prs, repository, default_branch, cutoff):
    """Return review candidates; this performs no deletion or live-state check."""
    open_branches = set()
    merged_heads = {}
    for pr in prs:
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        head_repo = (head.get("repo") or {}).get("full_name")
        base_repo = (base.get("repo") or {}).get("full_name")
        if pr.get("state") == "open":
            if head_repo == repository:
                open_branches.add(head.get("ref"))
            if base_repo == repository:
                open_branches.add(base.get("ref"))
        if head_repo != repository:
            continue
        name, sha = head.get("ref"), head.get("sha")
        if base_repo != repository:
            continue
        if base.get("ref") != default_branch or not pr.get("merged_at"):
            continue
        merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
        if merged_at <= cutoff and name and sha:
            merged_heads[(name, sha)] = pr["number"]

    result = []
    for branch in branches:
        name = branch["name"]
        sha = branch["commit"]["sha"]
        if name == default_branch or branch.get("protected") is not False:
            continue
        if name in open_branches:
            continue
        number = merged_heads.get((name, sha))
        if number is not None:
            result.append({"branch": name, "sha": sha, "merged_pr": number})
    return result
```

```python
for item in candidates(branches, prs, "OWNER/REPO", "main", cutoff):
    print(item["branch"], item["sha"], item["merged_pr"])
```

同名でも別forkの枝、マージ後に進んだhead、未完PR、保護状態が不明な枝、未完PRのbaseとして使われる枝などを外す10件のテストを実行しました。

[候補抽出のコードと10件のテスト](https://github.com/RollNuts/zenn-content/tree/505a71673bb5990749b00633ca4cb0e3c6eff9c9/examples/branch-cleanup-candidates)を公開しています。架空のPR・ブランチ情報だけを使い、Python 3.12で`python3.12 -m unittest -v`を実行できます。API接続やブランチの削除は行いません。

さらに、今回保存した556枝・548PRの応答をこの関数へ渡し、実際の整理候補453件と名前・SHAの組が一致することを確認しています。

## 先にバックアップを「戻して」確かめた

削除前のrefとGit履歴はmirrorとbundleに保存しました。bundleだけから別のmirrorを作り、ref名とSHAの一致を確認しています。

空の作業ディレクトリで試すと、概ね次の形です。

```sh
git clone --mirror https://github.com/OWNER/REPO.git backup.git
git -C backup.git bundle create ../branches.bundle --all
git clone --mirror branches.bundle restored.git
git -C restored.git fsck --full
git -C backup.git for-each-ref --format='%(refname) %(objectname)' > before.txt
git -C restored.git for-each-ref --format='%(refname) %(objectname)' > restored.txt
diff before.txt restored.txt
```

対象は、その時点でmirrorへ取得できた履歴とrefです。ローカルの未commit作業や、取得していない別repoの内容まで保存するものではありません。

今回の保存時点では、3,210コミットと、HEADを含む1,105のrefをbundleへ収めました。別mirrorへの復元、refの一致、`fsck`の成功を確認してから整理へ進みました。

## なぜ103本を残したか

残した内訳は次のとおりです。2026年11月8日の整理時点の記録で、現在のブランチ数を示す表ではありません。

| 残した理由 | 本数 |
| --- | ---: |
| 取り込みから24時間以内 | 30 |
| 未取り込み、または閉じただけのPR | 60 |
| 取り込み済みheadとの完全一致を確認できない | 12 |
| 既定ブランチmain | 1 |
| 合計 | 103 |

判定できないものを残す条件を先に決め、この103本を保持しました。

実際の削除では、各まとまりの前に未完PR・実行中のCI・commitのチェック状態を再取得しました。さらに削除直前に、各枝のSHAと保護状態が変わっていないことを確認しています。

ただし、今回使ったRESTのref削除は「このSHAのときだけ削除する」という比較交換ではありません。直前GETとDELETEの間の競合を完全に防ぐ仕組みにはなっていません。公開した候補関数も、この直前確認やCI確認、バックアップを代行しません。複数人やエージェントが更新中の環境で、候補の一覧をそのまま削除命令へ流す前提にはしないでください。

作業中には、別の[写真改善PR #551](https://github.com/RollNuts/mihassei-news/pull/551)がmainへ入りました。その更新は維持され、残したほかの102本は開始時とSHAが一致していました。最終照合では、対象453本の削除と、想定外の削除がないことを確認しています。

## 次に増やさないための設定

GitHubのマージ後ブランチ自動削除を有効にしました。保護規則の制約は維持しています。

持ち帰りたいのは、**祖先関係・PRの取り込み記録・現在のrefを、別々の根拠として確認する**ことです。squash merge後の枝を扱うときは、その区別が候補の見落としと、作業中の枝の混入を考える出発点になります。

対象は[未発生新聞の公開リポジトリ](https://github.com/RollNuts/mihassei-news)です。この記事の構成・コード例・集計と復元の検証には、コーディングエージェントを利用しています。


今回整理したrepoの実装例も紹介しています：[創作上の2031年をRSSに流さない――静的サイトで3つの日時を分ける](https://zenn.dev/veripsa/articles/fiction-date-rss-static-site)。
