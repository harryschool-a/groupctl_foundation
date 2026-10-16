# groupctl foundation — Version 0.1

This project is a starter implementation for the group collaboration assignment. It is a local helper, not a Dispatcher or an autonomous multi-agent system.

## Included so far

- `init`: create the required `.group/` scaffold, group configuration, member descriptor, and placeholder assignment file.
- `validate`: validate group configuration plus event common envelopes and documented payload fields for event types with explicit schemas in the Version 0.1 contract.
- `events`: list local event files and report whether their structure validates.
- `event-create`: create a local event from a JSON payload file, adding the common envelope from `.group/group.json` and `.group/members/`.
- Unit tests for configuration, event validation, event creation, and no-overwrite behavior.

The `final_candidate` and `final_result` event payload schemas will be completed together with the `FINAL` workflow because the Version 0.1 event contract names the required concepts but does not fully define those events' payload key names.

## Windows setup

Use Command Prompt or PowerShell in the folder that contains `groupctl.py`.

```cmd
python -m unittest discover -s tests -v
python groupctl.py init --group-id G-12 --person-id P17 --display-name "Student A"
python groupctl.py validate
python groupctl.py events
```

Run `init` only once in a repository. If `.group/group.json` already exists, skip `init`.

## Create a local event

Use the included example payload at `examples/finding_payload.json`. Then run:

```cmd
python groupctl.py event-create --event-type finding --payload-file examples/finding_payload.json
python groupctl.py validate
python groupctl.py events
```

When exactly one member descriptor exists, `groupctl` infers the person ID. In a multi-member repository, provide it explicitly, for example `--person-id P17`.

The `event-create` CLI subcommand is a low-level implementation helper; it is not one of the seven human-to-agent prompt commands. An event created on disk is **not yet published** to the group. The repository contract says it becomes public only after the file is staged, committed, and pushed using Git.

For a related event, add `--related-event EVENT_ID`; repeat the option if there are multiple related events.

## Not implemented yet

The seven prompt procedures (`SYNC`, `PUB`, `INT <change_id>`, `REV <change_id>`, `TEST [scope]`, `STATUS`, and `FINAL`) are not yet fully implemented. The portable AI-agent instruction file, Git-based publication/synchronization, and finalization workflow remain later milestones.
