import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import groupctl


class GroupConfigTests(unittest.TestCase):
    def test_valid_config_and_assignment_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".group/assignment").mkdir(parents=True)
            (root / ".group/assignment/assignment.md").write_text("# Assignment\n", encoding="utf-8")
            config = {
                "protocol_version": "0.1",
                "group_id": "G-12",
                "canonical_branch": "main",
                "assignment_file": ".group/assignment/assignment.md",
            }
            self.assertEqual(groupctl.validate_group_config(config, root), [])

    def test_missing_person_fields_are_reported(self):
        errors = groupctl.validate_group_config(
            {"protocol_version": "0.1", "group_id": "G-12"}, Path(".")
        )
        self.assertTrue(any("canonical_branch" in error for error in errors))
        self.assertTrue(any("assignment_file" in error for error in errors))


class EventValidationTests(unittest.TestCase):
    def valid_event(self):
        return {
            "protocol_version": "0.1",
            "event_id": "E-20261016T021530Z-P17-a91f",
            "event_type": "finding",
            "group_id": "G-12",
            "person_id": "P17",
            "created_at": "2026-10-16T02:15:30Z",
            "related_events": [],
            "summary": "A useful discovery.",
            "evidence": ["Reproduced in a test."],
        }

    def test_valid_common_envelope_and_finding_payload(self):
        event = self.valid_event()
        path = Path(f"{event['event_id']}.json")
        self.assertEqual(groupctl.validate_event(event, path), [])

    def test_missing_person_id_is_rejected(self):
        event = self.valid_event()
        del event["person_id"]
        errors = groupctl.validate_event(event)
        self.assertTrue(any("person_id" in error for error in errors))

    def test_unsupported_event_type_is_rejected(self):
        event = self.valid_event()
        event["event_type"] = "chat_dump"
        errors = groupctl.validate_event(event)
        self.assertTrue(any("event_type" in error for error in errors))

    def test_timestamp_must_have_timezone(self):
        event = self.valid_event()
        event["created_at"] = "2026-10-16T02:15:30"
        errors = groupctl.validate_event(event)
        self.assertTrue(any("timezone" in error for error in errors))

    def test_filename_must_match_event_id(self):
        event = self.valid_event()
        errors = groupctl.validate_event(event, Path("wrong-name.json"))
        self.assertTrue(any("filename must match event_id" in error for error in errors))

    def test_change_published_requires_documented_fields(self):
        event = self.valid_event()
        event.update({"event_type": "change_published", "summary": "Published", "evidence": []})
        errors = groupctl.validate_event(event)
        self.assertTrue(any("change_id" in error for error in errors))
        self.assertTrue(any("branch" in error for error in errors))
        self.assertTrue(any("proposed_for_integration" in error for error in errors))

    def test_review_rejects_unknown_verdict(self):
        event = self.valid_event()
        event.update({
            "event_type": "review", "change_id": "C-17", "verdict": "maybe",
            "summary": "Review", "issues": [], "tests_run": [],
        })
        errors = groupctl.validate_event(event)
        self.assertTrue(any("verdict must be one of" in error for error in errors))

    def test_all_documented_event_types_accept_their_contract_payloads(self):
        common = self.valid_event()
        payloads = {
            "change_published": {
                "change_id": "C-17", "branch": "people/P17/parser", "commit": "abc123",
                "summary": "Published parser", "files_changed": ["src/parser.py"],
                "interface_changes": [], "tests_run": ["python -m unittest"],
                "known_issues": [], "proposed_for_integration": True,
            },
            "finding": {"summary": "Found issue", "evidence": ["Reproduced"]},
            "question": {"question_id": "Q-1", "text": "Keep source positions?", "blocking": False},
            "answer": {"question_id": "Q-1", "text": "Yes."},
            "review": {"change_id": "C-17", "verdict": "accept", "summary": "Looks good", "issues": [], "tests_run": []},
            "test_result": {"scope": "main", "commit": "abc123", "commands": ["python -m unittest"], "automated_result": "pass", "passed": 2, "failed": 0, "skipped": 0, "human_checks_required": [], "summary": "Two passed"},
            "integration_result": {"change_id": "C-17", "target_branch": "people/P17/parser", "result": "success", "merge_commit": "def456", "conflicts": [], "verification": {"tests": "pass"}, "summary": "Integrated"},
            "blocker": {"summary": "Need interface decision", "requested_action": "Human chooses API", "blocking_change_id": "C-17"},
            "final_candidate": {"canonical_branch": "main", "canonical_commit": "a" * 40, "report_file": ".group/final/candidate.md", "summary": "Candidate", "completed_work": ["Feature"], "contributors": ["P17"], "test_evidence": ["Tests passed"], "known_limitations": [], "unresolved_concerns": []},
            "final_result": {"canonical_branch": "main", "canonical_commit": "a" * 40, "report_file": ".group/final/final_report.md", "initiated_by": "P17", "status": "completed", "summary": "Final", "test_evidence": ["Tests passed"], "known_limitations": []},
        }
        for event_type, payload in payloads.items():
            with self.subTest(event_type=event_type):
                event = {**common, "event_type": event_type, **payload}
                self.assertEqual(groupctl.validate_event(event, Path(f"{common['event_id']}.json")), [])

    def test_unhashable_enum_values_are_reported_not_crashed(self):
        review = self.valid_event()
        review.update({"event_type": "review", "change_id": "C-17", "verdict": [], "summary": "Review", "issues": [], "tests_run": []})
        self.assertTrue(any("verdict must be one of" in error for error in groupctl.validate_event(review)))
        test_event = self.valid_event()
        test_event.update({"event_type": "test_result", "scope": "current_branch", "commit": "abc123", "automated_result": [], "commands": [], "passed": 0, "failed": 0, "skipped": 0, "human_checks_required": [], "summary": "bad enum"})
        self.assertTrue(any("automated_result must be one of" in error for error in groupctl.validate_event(test_event)))

    def test_test_result_counts_must_be_nonnegative_integers(self):
        event = self.valid_event()
        event.update({
            "event_type": "test_result", "scope": "current_branch", "commit": "abc1234",
            "commands": ["python -m unittest"], "automated_result": "pass",
            "passed": -1, "failed": 0, "skipped": 0, "human_checks_required": [],
            "summary": "Tests passed.",
        })
        errors = groupctl.validate_event(event)
        self.assertTrue(any("passed must be a non-negative integer" in error for error in errors))


class EventCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_event_adds_common_envelope(self):
        path = groupctl.create_event(
            self.root, "finding",
            {"summary": "A useful discovery.", "evidence": ["A test reproduced it."]},
            None, [],
        )
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(path.parent, self.root / ".group/events")
        self.assertEqual(event["event_type"], "finding")
        self.assertEqual(event["group_id"], "G-12")
        self.assertEqual(event["person_id"], "P17")
        self.assertEqual(event["related_events"], [])
        self.assertEqual(groupctl.validate_event(event, path), [])

    def test_create_event_refuses_payload_to_override_common_fields(self):
        with self.assertRaisesRegex(ValueError, "common envelope fields"):
            groupctl.create_event(
                self.root, "finding",
                {"protocol_version": "9.9", "summary": "A finding", "evidence": []},
                None, [],
            )

    def test_create_event_requires_explicit_person_when_multiple_members_exist(self):
        groupctl.write_json(self.root / ".group/members/P22.json", {
            "protocol_version": "0.1", "person_id": "P22", "display_name": "Student B",
            "joined_at": "2026-10-16T10:30:00+08:00",
        })
        with self.assertRaisesRegex(ValueError, "Supply --person-id explicitly"):
            groupctl.create_event(
                self.root, "finding", {"summary": "A finding", "evidence": []}, None, []
            )

    def test_write_json_refuses_overwrite(self):
        path = self.root / ".group/events/test.json"
        groupctl.write_json(path, {"first": True})
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            groupctl.write_json(path, {"second": True})


@unittest.skipUnless(shutil.which("git"), "Git is required for remote-event integration tests")
class RemoteEventTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.root = base / "work"
        self.bare = base / "remote.git"
        self.root.mkdir()
        subprocess.run(["git", "init", "--bare", str(self.bare)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.git("config", "user.name", "Groupctl Test")
        self.git("config", "user.email", "groupctl-test@example.invalid")
        # Keep the test's committed blob bytes exact across Windows/Linux hosts.
        self.git("config", "core.autocrlf", "false")
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )
        self.git("add", ".")
        self.git("commit", "-m", "initialize test repository")
        self.git("remote", "add", "origin", str(self.bare))
        self.git("push", "--set-upstream", "origin", "main")
        self.git("checkout", "-b", "people/P17/demo")
        groupctl.create_event(
            self.root, "finding",
            {"summary": "Remote branch event", "evidence": ["Created in an integration test."]},
            None, [],
        )
        self.git("add", ".group/events")
        self.git("commit", "-m", "publish test event")
        self.git("push", "--set-upstream", "origin", "people/P17/demo")

    def current_event(self):
        event_path = next((self.root / ".group/events").glob("*.json"))
        return event_path, json.loads(event_path.read_text(encoding="utf-8"))

    def publish_file_on_branch(self, branch: str, relative_path: str, content: bytes, message: str):
        """Publish test bytes on a branch, then refresh remote-tracking refs."""
        self.git("checkout", branch)
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.git("add", "--", relative_path)
        self.git("commit", "-m", message)
        self.git("push", "origin", branch)
        self.git("fetch", "origin")

    def tearDown(self):
        self.temp_dir.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def run_remote_events(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = groupctl.main(["remote-events", "--root", str(self.root), *args])
        return code, output.getvalue()

    def test_discovers_event_on_remote_personal_branch(self):
        code, output = self.run_remote_events("--remote", "origin", "--new-only")
        self.assertEqual(code, 0, output)
        self.assertIn("NEW", output)
        self.assertIn("finding", output)
        self.assertIn("people/P17/demo", output)

    def test_mark_seen_checkpoint_prevents_relisting_known_events(self):
        code, first = self.run_remote_events("--remote", "origin", "--mark-seen")
        self.assertEqual(code, 0, first)
        self.assertIn("Checkpoint updated", first)
        code, second = self.run_remote_events("--remote", "origin", "--new-only")
        self.assertEqual(code, 0, second)
        self.assertIn("No new remote events since the last local checkpoint.", second)
        self.assertNotIn("finding", second)

    def test_malformed_remote_event_is_reported_and_not_checkpointed(self):
        self.publish_file_on_branch(
            "people/P17/demo", ".group/events/E-malformed.json", b"{ this is not JSON }\n",
            "add malformed event fixture",
        )

        code, output = self.run_remote_events("--remote", "origin", "--new-only", "--mark-seen")

        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", output)
        self.assertIn("Checkpoint not updated", output)
        self.assertFalse((self.root / ".group/local/known_remote_events_origin.json").exists())

    def test_remote_event_with_mismatched_group_id_is_rejected(self):
        _, event = self.current_event()
        event["event_id"] = "E-20261021T000000Z-P17-bad1"
        event["group_id"] = "G-OTHER"
        relative_path = f".group/events/{event['event_id']}.json"
        content = (json.dumps(event, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        self.publish_file_on_branch(
            "people/P17/demo", relative_path, content, "add mismatched group event fixture",
        )

        code, output = self.run_remote_events("--remote", "origin", "--new-only")

        self.assertEqual(code, 1)
        self.assertIn("group_id 'G-OTHER' does not match local group 'G-12'", output)
        self.assertIn("INVALID", output)

    def test_same_event_id_with_different_raw_line_endings_is_immutability_conflict(self):
        event_path, _event = self.current_event()
        # Save the exact bytes that were committed on people/P17/demo.
        original_bytes = event_path.read_bytes()
        self.assertIn(b"\n", original_bytes)
        self.assertNotIn(b"\r\n", original_bytes)

        # Create another remote branch from main, which has no finding event, then
        # publish the same JSON/event ID with CRLF bytes. JSON data is equivalent,
        # but a published event is immutable at the byte level.
        self.git("checkout", "-b", "people/P22/line-ending-conflict", "main")
        duplicate_path = self.root / ".group/events" / event_path.name
        duplicate_path.parent.mkdir(parents=True, exist_ok=True)
        duplicate_path.write_bytes(original_bytes.replace(b"\n", b"\r\n"))
        relative_path = duplicate_path.relative_to(self.root).as_posix()
        self.git("add", "--", relative_path)
        self.git("commit", "-m", "add byte-different duplicate event fixture")
        self.git("push", "--set-upstream", "origin", "people/P22/line-ending-conflict")
        self.git("fetch", "origin")

        code, output = self.run_remote_events("--remote", "origin", "--new-only")

        self.assertEqual(code, 1)
        self.assertIn("IMMUTABILITY CONFLICT", output)
        self.assertIn(event_path.stem, output)




@unittest.skipUnless(shutil.which("git"), "Git is required for finalization integration tests")
class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.git("config", "user.name", "Groupctl Finalization Test")
        self.git("config", "user.email", "groupctl-final-test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial canonical code")
        self.canonical_commit = self.git("rev-parse", "HEAD").strip()
        (self.root / ".group/local/candidate_payload.json").write_text(json.dumps({
            "canonical_branch": "main",
            "canonical_commit": self.canonical_commit,
            "summary": "The group implemented a small verified program.",
            "completed_work": ["Implemented answer()"],
            "contributors": ["P17 (Student A)"],
            "test_evidence": ["python -m unittest discover -s tests -v: pass"],
            "known_limitations": [],
            "unresolved_concerns": [],
        }, indent=2), encoding="utf-8")
        code, output = self.run_groupctl(
            "final-candidate", "--payload-file", ".group/local/candidate_payload.json", "--person-id", "P17"
        )
        self.assertEqual(code, 0, output)
        self.candidate_event_path = max((self.root / ".group/events").glob("*.json"), key=lambda x: x.stat().st_mtime)
        self.git("add", ".group/final/candidate.md", self.candidate_event_path.relative_to(self.root).as_posix())
        self.git("commit", "-m", "record final candidate")

    def tearDown(self):
        self.temp_dir.cleanup()

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout

    def run_groupctl(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = groupctl.main([args[0], "--root", str(self.root), *args[1:]])
        return code, output.getvalue()

    def final_payload(self, **updates):
        payload = {
            "canonical_branch": "main",
            "canonical_commit": self.canonical_commit,
            "summary": "The group implemented a small verified program.",
            "completed_work": ["Implemented answer()"],
            "contributors": ["P17 (Student A)"],
            "test_evidence": ["python -m unittest discover -s tests -v: pass"],
            "known_limitations": [],
            "status": "completed",
        }
        payload.update(updates)
        path = self.root / ".group/local/final_payload.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return ".group/local/final_payload.json"

    def test_candidate_creates_report_and_valid_event(self):
        self.assertTrue((self.root / ".group/final/candidate.md").is_file())
        events = [json.loads(p.read_text(encoding="utf-8")) for p in (self.root / ".group/events").glob("*.json")]
        candidates = [e for e in events if e["event_type"] == "final_candidate"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["canonical_commit"], self.canonical_commit)
        self.assertEqual(groupctl.validate_event(candidates[0]), [])

    def test_finalize_requires_explicit_human_confirmation(self):
        payload_path = self.final_payload()
        code, output = self.run_groupctl("finalize-confirmed", "--payload-file", payload_path, "--person-id", "P17")
        self.assertEqual(code, 1)
        self.assertIn("Human confirmation is required", output)
        self.assertFalse((self.root / ".group/final/final.json").exists())

    def test_finalize_writes_report_envelope_and_event_after_confirmation(self):
        payload_path = self.final_payload()
        code, output = self.run_groupctl(
            "finalize-confirmed", "--payload-file", payload_path, "--person-id", "P17", "--human-confirmed"
        )
        self.assertEqual(code, 0, output)
        report_path = self.root / ".group/final/final_report.md"
        envelope_path = self.root / ".group/final/final.json"
        self.assertTrue(report_path.is_file())
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        self.assertEqual(envelope["canonical_commit"], self.canonical_commit)
        self.assertEqual(envelope["status"], "completed")
        self.assertEqual(groupctl.validate_final_records(self.root, groupctl.read_json(self.root / ".group/group.json")), [])
        events = [json.loads(p.read_text(encoding="utf-8")) for p in (self.root / ".group/events").glob("*.json")]
        results = [e for e in events if e["event_type"] == "final_result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["canonical_commit"], self.canonical_commit)
        self.assertEqual(groupctl.validate_event(results[0]), [])

    def test_completed_status_requires_no_known_limitations(self):
        payload_path = self.final_payload(known_limitations=["One non-critical edge case is not supported."])
        code, output = self.run_groupctl(
            "finalize-confirmed", "--payload-file", payload_path, "--person-id", "P17", "--human-confirmed"
        )
        self.assertEqual(code, 1)
        self.assertIn("completed_with_known_limitations", output)

    def test_candidate_must_be_built_from_canonical_branch(self):
        self.git("checkout", "-b", "people/P17/experimental")
        payload = json.loads((self.root / ".group/local/candidate_payload.json").read_text(encoding="utf-8"))
        path = self.root / ".group/local/bad_candidate.json"
        payload["canonical_commit"] = self.git("rev-parse", "HEAD").strip()
        path.write_text(json.dumps(payload), encoding="utf-8")
        code, output = self.run_groupctl(
            "final-candidate", "--payload-file", ".group/local/bad_candidate.json", "--person-id", "P17"
        )
        self.assertEqual(code, 1)
        self.assertIn("configured canonical branch", output)

    def test_finalization_refuses_candidate_with_unresolved_concerns(self):
        payload = json.loads((self.root / ".group/local/candidate_payload.json").read_text(encoding="utf-8"))
        payload["unresolved_concerns"] = ["A published change is still unexplained."]
        payload["canonical_commit"] = self.git("rev-parse", "HEAD").strip()
        local_path = self.root / ".group/local/unresolved_candidate.json"
        local_path.write_text(json.dumps(payload), encoding="utf-8")
        code, output = self.run_groupctl("final-candidate", "--payload-file", ".group/local/unresolved_candidate.json", "--person-id", "P17", "--replace-candidate")
        self.assertEqual(code, 0, output)
        # Keep the candidate event committed as metadata, then the finalizer must
        # refuse final success because the latest proposal has unresolved concerns.
        candidate_events = list((self.root / ".group/events").glob("*.json"))
        newest_event = max(candidate_events, key=lambda x: x.stat().st_mtime)
        self.git("add", ".group/final/candidate.md", newest_event.relative_to(self.root).as_posix())
        self.git("commit", "-m", "revise final candidate with unresolved concern")
        final_path = self.final_payload(canonical_commit=payload["canonical_commit"])
        code, output = self.run_groupctl("finalize-confirmed", "--payload-file", final_path, "--person-id", "P17", "--human-confirmed")
        self.assertEqual(code, 1)
        self.assertIn("unresolved concerns", output)
        self.assertFalse((self.root / ".group/final/final.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
