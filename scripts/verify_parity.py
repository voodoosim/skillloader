#!/usr/bin/env python3
"""Verify the frozen Python baseline and Go catalog/search/load parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO / "testdata" / "parity"
FIXTURE_HOME = FIXTURE_DIR / "home"
QUERIES_PATH = FIXTURE_DIR / "frozen_queries.json"
LOADS_PATH = FIXTURE_DIR / "frozen_loads.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-loader",
        type=Path,
        default=Path.home() / ".codex" / "skills" / "skill-loader" / "scripts" / "skill_loader.py",
        help="path to the reference skill_loader.py",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def run_reference(loader: Path, *args: str) -> str:
    environment = os.environ.copy()
    environment["HOME"] = str(FIXTURE_HOME)
    completed = subprocess.run(
        [sys.executable, str(loader), *args],
        cwd=REPO,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def parse_search_output(output: str) -> list[dict]:
    results = []
    for line in output.splitlines():
        score, name, raw_tags = line.split("\t", 2)
        tags = [tag.removeprefix("#") for tag in raw_tags.split()]
        results.append({"score": int(score), "name": name, "tags": tags})
    return results


def verify_reference(loader: Path, queries: dict, loads: dict) -> None:
    if not loader.is_file():
        raise SystemExit(f"reference loader not found: {loader}")
    actual_hash = hashlib.sha256(loader.read_bytes()).hexdigest()
    expected_hash = queries["reference"]["sha256"]
    if actual_hash != expected_hash:
        raise SystemExit(
            f"reference loader checksum mismatch: got {actual_hash}, want {expected_hash}"
        )

    if len(queries["queries"]) != 10 or len(loads["loads"]) != 10:
        raise SystemExit("fixtures must contain exactly 10 searches and 10 loads")

    for fixture in queries["queries"]:
        output = run_reference(
            loader,
            "search",
            fixture["query"],
            "--limit",
            str(fixture["limit"]),
        )
        actual = parse_search_output(output)
        if actual != fixture["results"]:
            raise SystemExit(
                f"Python search mismatch for {fixture['id']}:\n"
                f"got  {json.dumps(actual, ensure_ascii=False)}\n"
                f"want {json.dumps(fixture['results'], ensure_ascii=False)}"
            )

    for fixture in loads["loads"]:
        actual = run_reference(loader, "load", fixture["name"])
        actual_hash = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        if actual != fixture["content"] or actual_hash != fixture["content_sha256"]:
            raise SystemExit(f"Python load mismatch for {fixture['name']}")

    print("python search parity: pass (10/10)")
    print("python exact-load parity: pass (10/10)")


def verify_go() -> bool:
    completed = subprocess.run(
        ["go", "test", "-v", "-count=1", "-run", "^TestPythonParityFixtures$", "."],
        cwd=REPO,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit("Go parity execution failed")

    match = re.search(r"PARITY_SUMMARY=(\{.*\})", completed.stdout)
    if match is None:
        raise SystemExit("Go parity summary was not emitted")
    summary = json.loads(match.group(1))

    checks = [
        (
            "go catalog parity",
            summary["catalog_matches"],
            summary["catalog_total"],
        ),
        (
            "go search top-1 parity",
            summary["top_one_matches"],
            summary["query_total"],
        ),
        (
            "go search exact-ranking parity",
            summary["exact_ranking_matches"],
            summary["query_total"],
        ),
        (
            "go exact-load parity",
            summary["load_matches"],
            summary["load_total"],
        ),
    ]
    passed = True
    for label, actual, total in checks:
        status = "pass" if actual == total else "fail"
        print(f"{label}: {status} ({actual}/{total})")
        passed = passed and actual == total
    return passed


def main() -> int:
    args = parse_args()
    queries = load_json(QUERIES_PATH)
    loads = load_json(LOADS_PATH)
    if queries.get("schema_version") != 1 or loads.get("schema_version") != 1:
        raise SystemExit("unsupported parity fixture schema")
    verify_reference(args.python_loader.resolve(), queries, loads)
    return 0 if verify_go() else 1


if __name__ == "__main__":
    raise SystemExit(main())
