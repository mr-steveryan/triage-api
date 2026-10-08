"""Run evals/case.json against a running Triage API server.

Usage: uv run python scripts/run_evals.py [base_url]   (default http://localhost:8000)
"""

import json
import sys
from collections import Counter
from pathlib import Path

import httpx

CASES_PATH = Path(__file__).parent.parent / "evals" / "case.json"
TIMEOUT_S = 35  # above the server's 30 s LLM budget, so the server's 504 arrives first


def check(case: dict, status: int, body: dict) -> list[tuple[str, object, object]]:
    """Return (field, expected, got) for every key field that did not match."""
    if status != 200:
        got = f"HTTP {status}"
        failed: list[tuple[str, object, object]] = [
            (f, v, got) for f, v in case["expected"].items()
        ]
        if "confidence_below" in case:
            failed.append(("confidence", f"< {case['confidence_below']}", got))
        return failed
    failed: list[tuple[str, object, object]] = [
        (f, v, body.get(f)) for f, v in case["expected"].items() if body.get(f) != v
    ]
    if "confidence_below" in case and not body["confidence"] < case["confidence_below"]:
        failed.append(
            ("confidence", f"< {case['confidence_below']}", body["confidence"])
        )
    return failed


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    checked, passed = Counter(), Counter()
    failures = []
    matched = 0

    with httpx.Client(base_url=base_url, timeout=TIMEOUT_S) as client:
        for case in cases:
            r = client.post("/triage", json={"support_message": case["input"]})
            body = r.json() if r.status_code == 200 else {}
            failed = check(case, r.status_code, body)
            fields = [*case["expected"]] + (
                ["confidence"] if "confidence_below" in case else []
            )
            failed_fields = {f for f, _, _ in failed}
            checked.update(fields)
            passed.update(f for f in fields if f not in failed_fields)
            matched += not failed
            failures += [(case["id"], *f) for f in failed]
            print(f"{'PASS' if not failed else 'FAIL'}  {case['id']}")

    print(f"\nMatched: {matched}/{len(cases)} ({matched / len(cases):.0%})")
    print("Per field:")
    for f in checked:
        print(f"  {f:<10} {passed[f]}/{checked[f]} ({passed[f] / checked[f]:.0%})")
    print("Failed fields:" if failures else "Failed fields: none")
    for case_id, f, want, got in failures:
        print(f"  {case_id}: {f} expected {want!r}, got {got!r}")


if __name__ == "__main__":
    main()
