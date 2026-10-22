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



if __name__ == "__main__":
    unittest.main(verbosity=2)
