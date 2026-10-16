#!/usr/bin/env python3
"""Version 0.1 group collaboration helper.

Implemented milestones:
- repository initialization;
- group and event validation;
- local creation and listing of immutable-format collaboration event files.

Git publication and the human-to-agent workflows (SYNC/PUB/INT/REV/TEST/STATUS/FINAL)
are implemented separately from these low-level CLI helper commands.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "0.1"
GROUP_DIR = Path(".group")
CONFIG_PATH = GROUP_DIR / "group.json"
DEFAULT_ASSIGNMENT_PATH = GROUP_DIR / "assignment" / "assignment.md"
EVENTS_DIR = GROUP_DIR / "events"
MEMBERS_DIR = GROUP_DIR / "members"
LOCAL_DIR = GROUP_DIR / "local"

SUPPORTED_EVENT_TYPES = {
    "change_published",
    "finding",
    "question",
    "answer",
    "review",
    "test_result",
    "integration_result",
    "blocker",
    "final_candidate",
    "final_result",
}

COMMON_EVENT_FIELDS = {
    "protocol_version",
    "event_id",
    "event_type",
    "group_id",
    "person_id",
    "created_at",
    "related_events",
}

REVIEW_VERDICTS = {"accept", "accept_with_changes", "reject", "needs_more_evidence"}
TEST_RESULTS = {"pass", "fail", "partial", "not_available"}
INTEGRATION_RESULTS = {"success", "failed", "needs_human"}


def read_json(path: Path) -> Any:
    """Read JSON and return the decoded value."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from exc
    except OSError as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write readable UTF-8 JSON, refusing to overwrite an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive mode is deliberate: published-format events are immutable and
    # unique names should not overwrite an earlier event.
    try:
        with path.open("x", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"Refusing to overwrite existing file: {path}") from exc


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_required_string_fields(data: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    for field in fields:
        if field not in data:
            errors.append(f"{data.get('event_type')} event is missing required field: {field}")
        elif not _is_nonempty_string(data[field]):
            errors.append(f"{field} must be a non-empty string.")
    return errors


def _validate_string_list_field(data: dict[str, Any], field: str, *, required: bool = True) -> list[str]:
    errors: list[str] = []
    if field not in data:
        if required:
            errors.append(f"{data.get('event_type')} event is missing required field: {field}")
        return errors
    value = data[field]
    if not isinstance(value, list):
        errors.append(f"{field} must be a JSON array of strings.")
    elif any(not isinstance(item, str) for item in value):
        errors.append(f"Every {field} item must be a string.")
    return errors


def validate_event_payload(data: dict[str, Any]) -> list[str]:
    """Validate the documented payload shape for event types with explicit examples.

    The final_candidate/final_result event concepts are documented in the contract,
    but their event payload key names are not fully enumerated there. Their complete
    validation will be added alongside the FINAL workflow rather than inventing a
    possibly incompatible schema here.
    """
    errors: list[str] = []
    event_type = data.get("event_type")

    if event_type == "change_published":
        errors.extend(_validate_required_string_fields(
            data, ("change_id", "branch", "commit", "summary")
        ))
        for field in ("files_changed", "interface_changes", "tests_run", "known_issues"):
            errors.extend(_validate_string_list_field(data, field))
        if "proposed_for_integration" not in data:
            errors.append("change_published event is missing required field: proposed_for_integration")
        elif not isinstance(data["proposed_for_integration"], bool):
            errors.append("proposed_for_integration must be a JSON boolean.")

    elif event_type == "finding":
        errors.extend(_validate_required_string_fields(data, ("summary",)))
        errors.extend(_validate_string_list_field(data, "evidence"))

    elif event_type == "question":
        errors.extend(_validate_required_string_fields(data, ("question_id", "text")))
        if "blocking" not in data:
            errors.append("question event is missing required field: blocking")
        elif not isinstance(data["blocking"], bool):
            errors.append("blocking must be a JSON boolean.")

    elif event_type == "answer":
        errors.extend(_validate_required_string_fields(data, ("question_id", "text")))

    elif event_type == "review":
        errors.extend(_validate_required_string_fields(data, ("change_id", "verdict", "summary")))
        if "verdict" in data and data["verdict"] not in REVIEW_VERDICTS:
            errors.append("verdict must be one of: " + ", ".join(sorted(REVIEW_VERDICTS)) + ".")
        errors.extend(_validate_string_list_field(data, "issues"))
        errors.extend(_validate_string_list_field(data, "tests_run"))

    elif event_type == "test_result":
        errors.extend(_validate_required_string_fields(data, ("scope", "commit", "automated_result", "summary")))
        errors.extend(_validate_string_list_field(data, "commands"))
        errors.extend(_validate_string_list_field(data, "human_checks_required"))
        if "automated_result" in data and data["automated_result"] not in TEST_RESULTS:
            errors.append("automated_result must be one of: " + ", ".join(sorted(TEST_RESULTS)) + ".")
        for field in ("passed", "failed", "skipped"):
            if field not in data:
                errors.append(f"test_result event is missing required field: {field}")
            elif isinstance(data[field], bool) or not isinstance(data[field], int) or data[field] < 0:
                errors.append(f"{field} must be a non-negative integer.")

    elif event_type == "integration_result":
        errors.extend(_validate_required_string_fields(data, ("change_id", "target_branch", "result", "summary")))
        if "result" in data and data["result"] not in INTEGRATION_RESULTS:
            errors.append("result must be one of: " + ", ".join(sorted(INTEGRATION_RESULTS)) + ".")
        errors.extend(_validate_string_list_field(data, "conflicts"))
        if "verification" not in data:
            errors.append("integration_result event is missing required field: verification")
        elif not isinstance(data["verification"], dict):
            errors.append("verification must be a JSON object.")
        else:
            for name, value in data["verification"].items():
                if not isinstance(name, str) or not isinstance(value, str):
                    errors.append("verification must map check names to string results.")
                    break
        if data.get("result") == "success":
            if not _is_nonempty_string(data.get("merge_commit")):
                errors.append("A successful integration_result must include a non-empty merge_commit.")
        if "conflict_resolution_summary" in data and not isinstance(data["conflict_resolution_summary"], str):
            errors.append("conflict_resolution_summary must be a string when provided.")

    elif event_type == "blocker":
        errors.extend(_validate_required_string_fields(data, ("summary", "requested_action")))
        if "blocking_change_id" in data and not _is_nonempty_string(data["blocking_change_id"]):
            errors.append("blocking_change_id must be a non-empty string when provided.")

    elif event_type in {"final_candidate", "final_result"}:
        # Avoid imposing undocumented payload key names before FINAL is implemented.
        if "canonical_commit" in data and not _is_nonempty_string(data["canonical_commit"]):
            errors.append("canonical_commit must be a non-empty string when provided.")

    return errors


def validate_group_config(data: Any, root: Path) -> list[str]:
    """Return validation errors for .group/group.json and its assignment path."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["group.json must contain a JSON object."]

    required_fields = ("protocol_version", "group_id", "canonical_branch", "assignment_file")
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if data.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(f"protocol_version must be {PROTOCOL_VERSION!r}.")

    for field in ("group_id", "canonical_branch", "assignment_file"):
        value = data.get(field)
        if field in data and not _is_nonempty_string(value):
            errors.append(f"{field} must be a non-empty string.")

    assignment_value = data.get("assignment_file")
    if isinstance(assignment_value, str) and assignment_value.strip():
        assignment_path = Path(assignment_value)
        if assignment_path.is_absolute() or ".." in assignment_path.parts:
            errors.append("assignment_file must be a repository-relative path without '..'.")
        elif not (root / assignment_path).is_file():
            errors.append(f"Assignment file does not exist: {assignment_value}")

    return errors


def validate_event(data: Any, expected_path: Path | None = None) -> list[str]:
    """Validate an event's common envelope and its documented payload fields."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Event must contain a JSON object."]

    for field in sorted(COMMON_EVENT_FIELDS):
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if data.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(f"protocol_version must be {PROTOCOL_VERSION!r}.")

    for field in ("event_id", "group_id", "person_id"):
        value = data.get(field)
        if field in data and not _is_nonempty_string(value):
            errors.append(f"{field} must be a non-empty string.")

    event_type = data.get("event_type")
    if not isinstance(event_type, str) or event_type not in SUPPORTED_EVENT_TYPES:
        errors.append("event_type must be one of: " + ", ".join(sorted(SUPPORTED_EVENT_TYPES)) + ".")
    else:
        errors.extend(validate_event_payload(data))

    related_events = data.get("related_events")
    if "related_events" in data:
        if not isinstance(related_events, list):
            errors.append("related_events must be a JSON array of event ID strings.")
        elif any(not isinstance(item, str) or not item.strip() for item in related_events):
            errors.append("Every related_events item must be a non-empty string.")

    created_at = data.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        parse_value = created_at[:-1] + "+00:00" if created_at.endswith("Z") else created_at
        try:
            parsed = datetime.fromisoformat(parse_value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                errors.append("created_at must include a timezone, such as Z or +08:00.")
        except ValueError:
            errors.append("created_at must be an ISO 8601 timestamp with a timezone.")
    elif "created_at" in data:
        errors.append("created_at must be a non-empty ISO 8601 timestamp string.")

    if expected_path is not None:
        event_id = data.get("event_id")
        if isinstance(event_id, str) and event_id and expected_path.name != f"{event_id}.json":
            errors.append(
                f"Event filename must match event_id: expected {event_id}.json, got {expected_path.name}."
            )

    return errors


def initialize_repository(root: Path, group_id: str, person_id: str, display_name: str,
                          canonical_branch: str, assignment_file: str) -> None:
    """Create the required collaboration directory scaffold without overwriting files."""
    root = root.resolve()
    normalized_assignment = assignment_file.replace("\\", "/")
    assignment_relative = Path(normalized_assignment)
    if assignment_relative.is_absolute() or ".." in assignment_relative.parts:
        raise ValueError("assignment_file must be a repository-relative path without '..'.")
    if not group_id.strip() or not canonical_branch.strip() or not person_id.strip() or not display_name.strip():
        raise ValueError("group_id, canonical_branch, person_id, and display_name must not be empty.")
    if "/" in person_id or "\\" in person_id or person_id in {".", ".."}:
        raise ValueError("person_id must be a single path-safe identifier, such as P17.")

    config_path = root / CONFIG_PATH
    member_path = root / MEMBERS_DIR / f"{person_id}.json"
    assignment_path = root / assignment_relative
    if config_path.exists():
        raise ValueError(f"{config_path} already exists; refusing to overwrite group configuration.")
    if member_path.exists():
        raise ValueError(f"{member_path} already exists; refusing to overwrite member descriptor.")

    for directory in (root / EVENTS_DIR, root / MEMBERS_DIR, root / LOCAL_DIR, assignment_path.parent):
        directory.mkdir(parents=True, exist_ok=True)

    config = {
        "protocol_version": PROTOCOL_VERSION,
        "group_id": group_id,
        "canonical_branch": canonical_branch,
        "assignment_file": normalized_assignment,
    }
    member = {
        "protocol_version": PROTOCOL_VERSION,
        "person_id": person_id,
        "display_name": display_name,
        "joined_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    write_json(config_path, config)
    write_json(member_path, member)
    if not assignment_path.exists():
        assignment_path.write_text(
            "# Group Assignment\n\nReplace this placeholder with the group's assignment description.\n",
            encoding="utf-8",
        )

    (root / LOCAL_DIR / ".gitkeep").touch(exist_ok=True)

    gitignore = root / ".gitignore"
    ignore_lines = [".group/local/*", "!.group/local/.gitkeep"]
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [line for line in ignore_lines if line not in existing]
    if missing:
        with gitignore.open("a", encoding="utf-8", newline="\n") as f:
            if existing and existing[-1] != "":
                f.write("\n")
            f.write("\n".join(missing) + "\n")


def _load_valid_group(root: Path) -> dict[str, Any]:
    config_path = root / CONFIG_PATH
    if not config_path.is_file():
        raise ValueError(f"Missing required configuration: {config_path}")
    config = read_json(config_path)
    config_errors = validate_group_config(config, root)
    if config_errors:
        raise ValueError("Invalid group configuration: " + "; ".join(config_errors))
    return config


def _resolve_person_id(root: Path, requested_person_id: str | None) -> str:
    members_dir = root / MEMBERS_DIR
    if not members_dir.is_dir():
        raise ValueError(f"Members directory does not exist: {members_dir}")

    if requested_person_id:
        if "/" in requested_person_id or "\\" in requested_person_id or requested_person_id in {".", ".."}:
            raise ValueError("person_id must be a single path-safe identifier, such as P17.")
        member_path = members_dir / f"{requested_person_id}.json"
        if not member_path.is_file():
            raise ValueError(f"No member descriptor found for person_id {requested_person_id!r}.")
        member = read_json(member_path)
        if not isinstance(member, dict) or member.get("person_id") != requested_person_id:
            raise ValueError(f"Member descriptor does not match person_id {requested_person_id!r}.")
        return requested_person_id

    member_paths = sorted(members_dir.glob("*.json"))
    if len(member_paths) != 1:
        raise ValueError(
            "Cannot infer the current person because the repository has "
            f"{len(member_paths)} member descriptor(s). Supply --person-id explicitly."
        )
    member = read_json(member_paths[0])
    if not isinstance(member, dict) or not _is_nonempty_string(member.get("person_id")):
        raise ValueError(f"Invalid member descriptor: {member_paths[0]}")
    if member_paths[0].name != f"{member['person_id']}.json":
        raise ValueError(f"Member filename must match person_id: {member_paths[0].name}")
    return member["person_id"]


def create_event(root: Path, event_type: str, payload: Any, person_id: str | None,
                 related_events: list[str]) -> Path:
    """Create a local event file from a payload, adding the common envelope."""
    root = root.resolve()
    config = _load_valid_group(root)
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError("Unsupported event type: " + event_type)
    if not isinstance(payload, dict):
        raise ValueError("Payload file must contain a JSON object.")

    reserved = sorted(COMMON_EVENT_FIELDS.intersection(payload.keys()))
    if reserved:
        raise ValueError(
            "Payload must not supply common envelope fields; groupctl creates these: "
            + ", ".join(reserved)
        )

    chosen_person_id = _resolve_person_id(root, person_id)
    if not isinstance(related_events, list) or any(not _is_nonempty_string(item) for item in related_events):
        raise ValueError("Each --related-event value must be a non-empty event ID.")

    now = datetime.now(timezone.utc)
    timestamp_id = now.strftime("%Y%m%dT%H%M%SZ")
    events_dir = root / EVENTS_DIR
    events_dir.mkdir(parents=True, exist_ok=True)

    # A short UUID suffix keeps simultaneous events from getting the same name.
    while True:
        event_id = f"E-{timestamp_id}-{chosen_person_id}-{uuid.uuid4().hex[:4]}"
        event_path = events_dir / f"{event_id}.json"
        if not event_path.exists():
            break

    event: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "group_id": config["group_id"],
        "person_id": chosen_person_id,
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "related_events": related_events,
        **payload,
    }
    errors = validate_event(event, event_path)
    if errors:
        raise ValueError("Event payload is invalid: " + "; ".join(errors))

    write_json(event_path, event)
    return event_path


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        initialize_repository(
            root=root,
            group_id=args.group_id,
            person_id=args.person_id,
            display_name=args.display_name,
            canonical_branch=args.canonical_branch,
            assignment_file=args.assignment_file,
        )
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Initialized group collaboration metadata in: {root.resolve() / GROUP_DIR}")
    print(f"Group ID: {args.group_id}")
    print(f"Canonical branch: {args.canonical_branch}")
    print(f"Member: {args.person_id} ({args.display_name})")
    print("Next: run `python groupctl.py validate --root .` from the repository root.")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    config_path = root / CONFIG_PATH
    if not config_path.is_file():
        print(f"ERROR: Missing required configuration: {config_path}", file=sys.stderr)
        return 1

    try:
        config = read_json(config_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors = validate_group_config(config, root)
    if errors:
        print("Group configuration: INVALID")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Group configuration: OK")

    events_dir = root / EVENTS_DIR
    event_count = 0
    event_errors: list[str] = []
    if events_dir.exists():
        for event_path in sorted(events_dir.glob("*.json")):
            event_count += 1
            try:
                event_data = read_json(event_path)
                for error in validate_event(event_data, event_path):
                    event_errors.append(f"{event_path.relative_to(root)}: {error}")
            except ValueError as exc:
                event_errors.append(str(exc))

    if event_errors:
        print(f"Events: INVALID ({event_count} file(s) checked)")
        for error in event_errors:
            print(f"  - {error}")
    else:
        print(f"Events: OK ({event_count} file(s) checked)")

    return 1 if errors or event_errors else 0


def command_list_events(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    events_dir = root / EVENTS_DIR
    if not events_dir.is_dir():
        print(f"ERROR: Events directory does not exist: {events_dir}", file=sys.stderr)
        return 1

    files = sorted(events_dir.glob("*.json"))
    if not files:
        print("No collaboration events found.")
        return 0

    for path in files:
        try:
            data = read_json(path)
        except ValueError as exc:
            print(f"INVALID  {path.name}: {exc}")
            continue
        errors = validate_event(data, path)
        if errors:
            print(f"INVALID  {path.name}: {'; '.join(errors)}")
        else:
            print(f"OK       {data['event_type']:<20} {data['event_id']} (person {data['person_id']})")
    return 0


def command_event_create(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    payload_path = Path(args.payload_file)
    if not payload_path.is_absolute():
        payload_path = root / payload_path
    try:
        payload = read_json(payload_path)
        event_path = create_event(
            root=root,
            event_type=args.event_type,
            payload=payload,
            person_id=args.person_id,
            related_events=args.related_event,
        )
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Created local event: {event_path.relative_to(root)}")
    print(f"Event type: {args.event_type}")
    print("This event is local only until it is committed and pushed with Git.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groupctl",
        description="Version 0.1 group collaboration repository helper.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create the required .group/ scaffold")
    init_parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    init_parser.add_argument("--group-id", required=True, help="shared group identifier, e.g. G-12")
    init_parser.add_argument("--person-id", required=True, help="your member identifier, e.g. P17")
    init_parser.add_argument("--display-name", required=True, help="your display name")
    init_parser.add_argument("--canonical-branch", default="main", help="configured canonical branch (default: main)")
    init_parser.add_argument("--assignment-file", default=str(DEFAULT_ASSIGNMENT_PATH).replace("\\", "/"),
                             help="repository-relative assignment path")
    init_parser.set_defaults(func=command_init)

    validate_parser = subparsers.add_parser("validate", help="validate group configuration and event files")
    validate_parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    validate_parser.set_defaults(func=command_validate)

    events_parser = subparsers.add_parser("events", help="list and validate event files")
    events_parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    events_parser.set_defaults(func=command_list_events)

    event_create_parser = subparsers.add_parser(
        "event-create", help="create a validated local event from a JSON payload file"
    )
    event_create_parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    event_create_parser.add_argument("--event-type", required=True, choices=sorted(SUPPORTED_EVENT_TYPES))
    event_create_parser.add_argument("--payload-file", required=True,
                                     help="JSON file containing event-specific fields only")
    event_create_parser.add_argument("--person-id", help="member ID (inferred if exactly one member exists)")
    event_create_parser.add_argument("--related-event", action="append", default=[],
                                     help="related event ID; may be supplied multiple times")
    event_create_parser.set_defaults(func=command_event_create)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
