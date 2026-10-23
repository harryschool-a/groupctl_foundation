#!/usr/bin/env python3
"""Run a disposable three-member Git collaboration demonstration.

The script creates a temporary bare Git remote and three local clones. It does
not touch the repository where the script is stored and does not contact GitHub.
Use --auto-confirm-final only for a fully automated, explicitly simulated final
confirmation; without it, the script asks the human to type FINALIZE.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import groupctl  # noqa: E402


def run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}:\n{result.stdout}\n{result.stderr}"
        )
    return result


def run_tool(root: Path, *args: str, expect: int = 0) -> str:
    from contextlib import redirect_stdout, redirect_stderr
    from io import StringIO

    output = StringIO()
    with redirect_stdout(output), redirect_stderr(output):
        code = groupctl.main([*args[:1], "--root", str(root), *args[1:]])
    text = output.getvalue()
    if code != expect:
        raise RuntimeError(f"groupctl {' '.join(args)} returned {code}, expected {expect}:\n{text}")
    print(text.rstrip())
    return text


def configure(cwd: Path, name: str, email: str) -> None:
    run_git(cwd, "config", "user.name", name)
    run_git(cwd, "config", "user.email", email)
    run_git(cwd, "config", "core.autocrlf", "true")


def commit_all(cwd: Path, message: str, *paths: str) -> str:
    if paths:
        run_git(cwd, "add", "--", *paths)
    else:
        run_git(cwd, "add", "-A")
    check = run_git(cwd, "diff", "--cached", "--check")
    if check.returncode != 0:
        raise RuntimeError(f"Staged whitespace check failed:\n{check.stdout}\n{check.stderr}")
    run_git(cwd, "commit", "-m", message)
    return run_git(cwd, "rev-parse", "HEAD").stdout.strip()


def publish_event(cwd: Path, event_type: str, payload: dict[str, Any], person_id: str, message: str,
                  related_events: list[str] | None = None) -> tuple[Path, str]:
    path = groupctl.create_event(cwd, event_type, payload, person_id, related_events or [])
    rel = path.relative_to(cwd).as_posix()
    sha = commit_all(cwd, message, rel)
    return path, sha


def publish_change(cwd: Path, person_id: str, branch: str, summary: str,
                   files_changed: list[str], interface_changes: list[str], tests_run: list[str],
                   known_issues: list[str] | None = None) -> tuple[str, str]:
    code_commit = run_git(cwd, "rev-parse", "HEAD").stdout.strip()
    change_id = f"C-{code_commit[:7]}"
    path, _event_commit = publish_event(cwd, "change_published", {
        "change_id": change_id,
        "branch": branch,
        "commit": code_commit,
        "summary": summary,
        "files_changed": files_changed,
        "interface_changes": interface_changes,
        "tests_run": tests_run,
        "known_issues": known_issues or [],
        "proposed_for_integration": True,
    }, person_id, f"chore(events): publish {change_id}")
    run_git(cwd, "push", "-u", "origin", branch)
    return change_id, json.loads(path.read_text(encoding="utf-8"))["event_id"]


def run_tests(cwd: Path) -> tuple[int, int, str]:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    output = result.stdout
    match = re.search(r"Ran (\d+) tests? in", output)
    count = int(match.group(1)) if match else 0
    if result.returncode != 0:
        raise RuntimeError(f"Test suite failed in {cwd}:\n{output}")
    print(f"Tests passed in {cwd.name}: {count} test(s)")
    return count, 0, " ".join(command)


def copy_project_files(destination: Path) -> None:
    ignore = shutil.ignore_patterns(
        ".git", ".group", "__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache", ".ruff_cache"
    )
    shutil.copytree(REPO_ROOT, destination, dirs_exist_ok=True, ignore=ignore)


def add_member(root: Path, person_id: str, name: str) -> None:
    groupctl.write_json(root / ".group" / "members" / f"{person_id}.json", {
        "protocol_version": "0.1",
        "person_id": person_id,
        "display_name": name,
        "joined_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })


def write_text(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def demo(auto_confirm_final: bool) -> None:
    if shutil.which("git") is None:
        raise RuntimeError("Git is required for the demo. Install Git for Windows or Git before running it.")

    with tempfile.TemporaryDirectory(prefix="groupctl-three-member-demo-") as temporary:
        temp = Path(temporary)
        bare = temp / "shared.git"
        seed = temp / "seed"
        a = temp / "person_a"
        b = temp / "person_b"
        c = temp / "person_c"
        seed.mkdir()
        run_git(temp, "init", "--bare", str(bare))
        run_git(seed, "init", "-b", "main")
        configure(seed, "Demo Student A", "student-a@example.invalid")
        copy_project_files(seed)
        groupctl.initialize_repository(seed, "G-DEMO", "P17", "Student A", "main", ".group/assignment/assignment.md")
        add_member(seed, "P22", "Student B")
        add_member(seed, "P31", "Student C")
        write_text(seed, "src/__init__.py", "")
        write_text(seed, "src/shared.py", 'MODE = "base"\n')
        commit_all(seed, "initialize shared group repository")
        run_git(seed, "remote", "add", "origin", str(bare))
        run_git(seed, "push", "-u", "origin", "main")
        run_git(bare, "symbolic-ref", "HEAD", "refs/heads/main")

        for path, who, email in ((a, "Student A", "student-a@example.invalid"),
                                 (b, "Student B", "student-b@example.invalid"),
                                 (c, "Student C", "student-c@example.invalid")):
            run_git(temp, "clone", "--branch", "main", str(bare), str(path))
            configure(path, who, email)

        print("\n=== A: independently implement and publish parser ===")
        run_git(a, "switch", "-c", "people/P17/parser")
        write_text(a, "src/parser.py", 'def parse(value: str) -> dict[str, str]:\n    return {"value": value.strip()}\n')
        write_text(a, "tests/test_parser_feature.py", (
            "import unittest\nfrom src.parser import parse\n\n"
            "class ParserFeatureTests(unittest.TestCase):\n"
            "    def test_parse_strips_whitespace(self):\n"
            "        self.assertEqual(parse('  demo  '), {'value': 'demo'})\n"
        ))
        run_tests(a)
        commit_all(a, "feat(parser): add parse helper", "src/parser.py", "tests/test_parser_feature.py")
        change_a, event_a = publish_change(
            a, "P17", "people/P17/parser", "Add a parser that normalizes input whitespace.",
            ["src/parser.py", "tests/test_parser_feature.py"],
            ["Introduces parse(value: str) -> dict[str, str]."],
            ["python -m unittest discover -s tests -v"],
        )
        print(f"Published {change_a} via event {event_a}")

        print("\n=== B: independently implement and publish renderer ===")
        run_git(b, "switch", "-c", "people/P22/renderer")
        write_text(b, "src/renderer.py", 'def render(value: str) -> str:\n    return f"<{value}>"\n')
        write_text(b, "src/shared.py", 'MODE = "renderer"\n')
        write_text(b, "tests/test_renderer_feature.py", (
            "import unittest\nfrom src.renderer import render\n\n"
            "class RendererFeatureTests(unittest.TestCase):\n"
            "    def test_render_adds_brackets(self):\n"
            "        self.assertEqual(render('demo'), '<demo>')\n"
        ))
        run_tests(b)
        commit_all(b, "feat(renderer): add renderer and mode", "src/renderer.py", "src/shared.py", "tests/test_renderer_feature.py")
        change_b, event_b = publish_change(
            b, "P22", "people/P22/renderer", "Add renderer and declare renderer mode.",
            ["src/renderer.py", "src/shared.py", "tests/test_renderer_feature.py"],
            ["Introduces render(value: str) -> str; shared MODE becomes renderer."],
            ["python -m unittest discover -s tests -v"],
        )
        print(f"Published {change_b} via event {event_b}")

        print("\n=== B: SYNC discovers A's event, then cleanly integrates A ===")
        run_git(b, "fetch", "origin", "--prune")
        run_tool(b, "remote-events", "--remote", "origin", "--new-only")
        run_git(b, "merge", "--no-ff", "origin/people/P17/parser", "-m", f"integrate {change_a}")
        run_tests(b)
        clean_merge_commit = run_git(b, "rev-parse", "HEAD").stdout.strip()
        path_a, _ = publish_event(b, "integration_result", {
            "change_id": change_a,
            "target_branch": "people/P22/renderer",
            "result": "success",
            "merge_commit": clean_merge_commit,
            "conflicts": [],
            "verification": {"git_merge": "pass", "unit_tests": "pass", "semantic_review": "pass"},
            "summary": "Integrated parser contribution into renderer branch; tests and API assumptions were checked.",
        }, "P22", f"chore(events): record integration of {change_a}", [event_a])
        run_git(b, "push", "origin", "people/P22/renderer")
        print(f"Clean integration recorded in {path_a.name}")

        print("\n=== C: publish a deliberately conflicting shared-mode change ===")
        run_git(c, "switch", "-c", "people/P31/tests")
        write_text(c, "src/shared.py", 'MODE = "tests"\n')
        write_text(c, "tests/test_shared_mode.py", (
            "import unittest\nfrom src.shared import MODE\n\n"
            "class SharedModeIntegrationTests(unittest.TestCase):\n"
            "    def test_combined_mode_preserves_both_contributions(self):\n"
            "        self.assertEqual(MODE, 'renderer+tests')\n"
        ))
        # This change's integration test is deliberately intended to pass after
        # the conflict is resolved against B's renderer mode.
        commit_all(c, "test: add shared mode integration expectation", "src/shared.py", "tests/test_shared_mode.py")
        change_c, event_c = publish_change(
            c, "P31", "people/P31/tests", "Add a shared-mode integration expectation.",
            ["src/shared.py", "tests/test_shared_mode.py"],
            ["Tests require the combined mode to preserve both renderer and test intent."],
            ["Shared-mode test is evaluated after conflict resolution."],
            ["The isolated branch conflicts semantically with the renderer branch until integrated."],
        )
        print(f"Published {change_c} via event {event_c}")

        print("\n=== B: detect the merge conflict, resolve both intents, and verify ===")
        run_git(b, "fetch", "origin", "--prune")
        run_tool(b, "remote-events", "--remote", "origin", "--new-only")
        attempted = run_git(b, "merge", "--no-ff", "origin/people/P31/tests", "-m", f"integrate {change_c}", check=False)
        if attempted.returncode == 0:
            raise RuntimeError("Expected a deliberate conflict in src/shared.py, but Git merged without conflict.")
        conflict_status = run_git(b, "status", "--short").stdout
        if "src/shared.py" not in conflict_status:
            raise RuntimeError(f"Git failed for a reason other than the expected src/shared.py conflict:\n{attempted.stdout}\n{attempted.stderr}\n{conflict_status}")
        print("Git reported the expected conflict in src/shared.py.")
        write_text(b, "src/shared.py", 'MODE = "renderer+tests"\n')
        commit_all(b, f"merge: resolve shared-mode conflict for {change_c}", "src/shared.py")
        run_tests(b)
        conflict_merge_commit = run_git(b, "rev-parse", "HEAD").stdout.strip()
        path_c, _ = publish_event(b, "integration_result", {
            "change_id": change_c,
            "target_branch": "people/P22/renderer",
            "result": "success",
            "merge_commit": conflict_merge_commit,
            "conflicts": ["src/shared.py"],
            "conflict_resolution_summary": "Combined the renderer's mode with the testing contribution as renderer+tests; the shared-mode test then passed.",
            "verification": {"git_merge": "pass_after_manual_resolution", "unit_tests": "pass", "semantic_review": "pass"},
            "summary": "Resolved the deliberate shared-mode conflict after preserving both contributions and rerunning the tests.",
        }, "P22", f"chore(events): record conflict resolution for {change_c}", [event_c])
        run_git(b, "push", "origin", "people/P22/renderer")
        print(f"Conflict integration recorded in {path_c.name}")

        print("\n=== Canonical integration: C fast-forwards main to the accepted group state ===")
        run_git(c, "fetch", "origin", "--prune")
        run_git(c, "switch", "main")
        run_git(c, "merge", "--ff-only", "origin/people/P22/renderer")
        run_tests(c)
        tested_commit = run_git(c, "rev-parse", "HEAD").stdout.strip()
        test_output = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=c, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
        ).stdout
        count_match = re.search(r"Ran (\d+) tests? in", test_output)
        passed_count = int(count_match.group(1)) if count_match else 0
        test_event_path, _ = publish_event(c, "test_result", {
            "scope": "canonical main",
            "commit": tested_commit,
            "commands": ["python -m unittest discover -s tests -v"],
            "automated_result": "pass",
            "passed": passed_count,
            "failed": 0,
            "skipped": 0,
            "human_checks_required": ["This is a local simulated workflow; live GitHub permissions/network and independent AI judgment were not exercised by the demo."],
            "summary": f"All {passed_count} repository tests passed on the canonical code commit.",
        }, "P31", "chore(events): publish canonical test result", [path_a.stem, path_c.stem])
        run_git(c, "push", "origin", "main")
        print(f"Test evidence published: {test_event_path.name}; tested commit {tested_commit}")

        print("\n=== FINAL: prepare candidate, show it, and require confirmation ===")
        final_candidate_commit = run_git(c, "rev-parse", "HEAD").stdout.strip()
        limitation = "Demonstration uses a temporary local bare Git remote and three simulated clones; live GitHub authentication, permissions, and independent AI-agent behavior remain to be demonstrated by the student group."
        candidate_payload = {
            "canonical_branch": "main",
            "canonical_commit": final_candidate_commit,
            "summary": "Three simulated members published separate work, discovered shared events, integrated a clean change, resolved a deliberate conflict, tested the combined code, and published test evidence.",
            "completed_work": [
                f"P17 published parser change {change_a}.",
                f"P22 published renderer change {change_b} and cleanly integrated {change_a}.",
                f"P31 published shared-mode test change {change_c}.",
                "P22 resolved a deliberately generated src/shared.py conflict while preserving both contributions.",
                "The combined test suite passed on canonical main and a test_result event was published.",
            ],
            "contributors": ["P17 (Student A)", "P22 (Student B)", "P31 (Student C)"],
            "test_evidence": [
                f"python -m unittest discover -s tests -v: {passed_count} tests passed on commit {tested_commit}.",
                "Clean integration of parser contribution: verified by Git merge and tests.",
                "Deliberate src/shared.py merge conflict: detected, resolved, and verified by the shared-mode test.",
                f"Published test_result event {json.loads(test_event_path.read_text(encoding='utf-8'))['event_id']}.",
            ],
            "known_limitations": [limitation],
            "unresolved_concerns": [],
        }
        candidate_payload_path = c / ".group/local/demo_candidate_payload.json"
        candidate_payload_path.write_text(json.dumps(candidate_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run_tool(c, "final-candidate", "--payload-file", ".group/local/demo_candidate_payload.json", "--person-id", "P31",
                 "--related-event", json.loads(test_event_path.read_text(encoding="utf-8"))["event_id"])
        print("\n--- .group/final/candidate.md ---")
        print((c / ".group/final/candidate.md").read_text(encoding="utf-8"))
        candidate_event_path = max((c / ".group/events").glob("*.json"), key=lambda path: path.stat().st_mtime)
        commit_all(c, "chore(final): record final candidate", ".group/final/candidate.md", candidate_event_path.relative_to(c).as_posix())
        run_git(c, "push", "origin", "main")

        if not auto_confirm_final:
            try:
                answer = input("Type FINALIZE only if you explicitly approve this candidate: ").strip()
            except EOFError:
                answer = ""
            if answer != "FINALIZE":
                print("Stopped after candidate creation. No final_result was created.")
                print("The temporary demo repository will be removed at exit.")
                return

        final_payload = {
            "canonical_branch": "main",
            "canonical_commit": final_candidate_commit,
            "summary": candidate_payload["summary"],
            "completed_work": candidate_payload["completed_work"],
            "contributors": candidate_payload["contributors"],
            "test_evidence": candidate_payload["test_evidence"],
            "known_limitations": candidate_payload["known_limitations"],
            "status": "completed_with_known_limitations",
        }
        final_payload_path = c / ".group/local/demo_final_payload.json"
        final_payload_path.write_text(json.dumps(final_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run_tool(c, "finalize-confirmed", "--payload-file", ".group/local/demo_final_payload.json", "--person-id", "P31", "--human-confirmed",
                 "--related-event", json.loads(candidate_event_path.read_text(encoding="utf-8"))["event_id"])
        final_event = max(
            (path for path in (c / ".group/events").glob("*.json")
             if json.loads(path.read_text(encoding="utf-8")).get("event_type") == "final_result"),
            key=lambda path: path.stat().st_mtime,
        )
        commit_all(c, "chore(final): publish final group records",
                   ".group/final/final_report.md", ".group/final/final.json", final_event.relative_to(c).as_posix())
        run_git(c, "push", "origin", "main")
        run_tool(c, "validate")
        print("\nDEMO SUCCESS")
        print(f"Temporary bare remote: {bare}")
        print(f"Canonical branch: main")
        print(f"Final canonical code commit: {final_candidate_commit}")
        print("Final report: .group/final/final_report.md")
        print("Final JSON: .group/final/final.json")
        print("The temporary demo repo will be removed automatically when this script exits.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auto-confirm-final", action="store_true",
        help="simulate an explicit human confirmation for a non-interactive demonstration",
    )
    args = parser.parse_args()
    try:
        demo(args.auto_confirm_final)
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"DEMO FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
