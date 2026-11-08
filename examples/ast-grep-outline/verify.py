"""Check the article's small, synthetic TypeScript fixture with a pinned CLI."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify(executable):
    binary = shutil.which(executable)
    if binary is None:
        raise RuntimeError("ast-grep not found; pass --ast-grep with the installed path")
    binary = str(Path(binary).resolve())
    version = subprocess.check_output([binary, "--version"], text=True, timeout=10).strip()
    if version != "ast-grep 0.51.1":
        raise RuntimeError("This fixture is pinned to ast-grep 0.51.1; observed " + version)
    observations = []

    def outline(*args):
        command = [binary, "outline", *args, "--json=compact"]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                timeout=10, check=True)
        payload = json.loads(result.stdout)
        observations.append({"arguments": command[1:], "files": payload})
        return payload

    def items(rows):
        return [item for row in rows for item in row["items"]]

    checks = []
    file_items = items(outline("src/catalog.ts"))
    assert {x["name"] for x in file_items} == {
        "Product", "normalizeSku", "Catalog", "API_BASE", "explanation"}
    assert not {"commentOnly", "stringOnly"} & {x["name"] for x in file_items}
    checks.append("file default includes local declarations; fake declarations are not items")

    directory_items = items(outline("src"))
    assert not {"normalizeSku", "explanation"} & {x["name"] for x in directory_items}
    assert {"Catalog", "Product", "API_BASE", "productLabel"} <= {
        x["name"] for x in directory_items}
    checks.append("directory default selects exported items")

    exported = items(outline("src/catalog.ts", "--items", "exports", "--view", "expanded",
                             "--pub-members"))
    catalog = next(x for x in exported if x["name"] == "Catalog")
    assert {x["name"] for x in catalog["members"]} == {"constructor", "lookup"}
    base = next(x for x in exported if x["name"] == "API_BASE")
    assert '"https://example.invalid/catalog"' in base["signature"]
    checks.append("public member filter hides private members but preserves constant values")

    imports = items(outline("src/label.ts", "--items", "imports"))
    assert len(imports) == 1 and imports[0]["isImport"]
    assert '"./catalog"' in imports[0]["signature"]
    checks.append("imports show the local import syntax")

    reexports = items(outline("src/index.ts", "--items", "all", "--view", "expanded"))
    assert len(reexports) == 3
    assert all(x["symbolType"] == "module" and not x.get("members", []) for x in reexports)
    checks.append("re-export entries do not expand target class members")

    assert items(outline("src/catalog.ts", "--match", "isEmpty")) == []
    chosen = items(outline("src/catalog.ts", "--match", "Catalog", "--view", "expanded"))
    assert {x["name"] for x in chosen[0]["members"]} == {
        "constructor", "lookup", "products", "isEmpty"}
    checks.append("match filters top-level items, not member names")

    raw = (ROOT / "src/catalog.ts").read_bytes()
    for item in file_items:
        if item["name"] != "Catalog":
            continue
        start = item["range"]["start"]["line"]
        assert raw.decode().splitlines()[start] == "export class Catalog {"
        offsets = item["range"]["byteOffset"]
        assert raw[offsets["start"]:offsets["end"]].startswith(b"export class Catalog {")
    checks.append("JSON line numbers are zero-based and byte ranges point into the fixture")

    return {"version": version, "passed": len(checks), "checks": checks,
            "fixture_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted((ROOT / "src").glob("*.ts"))},
            "observations": observations}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ast-grep", default="ast-grep")
    parser.add_argument("--report", type=Path, help="Optionally save the complete CLI observations")
    args = parser.parse_args()
    try:
        report = verify(args.ast_grep)
    except (AssertionError, RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
        parser.exit(1, f"Verification failed: {error}\n")
    if args.report is not None:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("version", "passed", "checks")},
                     ensure_ascii=False, indent=2))
