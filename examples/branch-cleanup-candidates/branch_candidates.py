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
