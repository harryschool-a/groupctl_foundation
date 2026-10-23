# `groupctl` — Group Collaboration Helper, Version 0.1

This project implements the first collaboration layer for several **human + local AI agent pairs working as one programming group through a shared Git repository**. Git manages commits, branches, and merges; `groupctl` validates and records standardized engineering events; `AGENT_INSTRUCTIONS.md` tells the local AI agent how to execute the seven human prompt commands consistently.

This is not the Dispatcher, not a task-planning brain, and not a complete autonomous multi-agent system. Version 0.1 needs no AI-vendor API or separate server.

## Included

- `groupctl.py`: deterministic local helper.
- `AGENT_INSTRUCTIONS.md`: portable agent procedures for `SYNC`, `PUB`, `INT`, `REV`, `TEST`, `STATUS`, and `FINAL`.
- `.group/` repository contract is created at initialization and follows the supplied specifications.
- JSON event validation for all ten documented event types.
- Immutable event creation, validation, and local listing.
- Read-only event discovery on already-fetched remote branches, with raw-blob byte hashes for immutability checks and a local-only “inspected” checkpoint.
- Final candidate generation and confirmed finalization helpers. They refuse finalization without explicit confirmation, require the configured canonical branch, check unresolved candidate concerns, and protect against source-code changes after the candidate commit.
- Unit tests including local-Git-remote integration tests.
- A three-member local demo that exercises independent branches, publication, remote event discovery, a clean merge, a deliberate merge conflict, post-merge tests, a test-result event, and finalization against a temporary bare Git remote.
- The provided specifications copied into `specifications/` for reference.

## Requirements

- Python 3.10 or newer is recommended.
- Git must be installed and available on `PATH` for remote-event inspection, finalization helpers, and integration tests.
- No third-party Python dependencies are required.

## Windows quick start

Open PowerShell in the folder containing `groupctl.py`:

```powershell
python --version
python -m unittest discover -s tests -v
python groupctl.py init --group-id G-12 --person-id P17 --display-name "Student A"
python groupctl.py validate
python groupctl.py events
```

Run `init` only once. If `.group/group.json` already exists, do not initialize again; run `validate` instead. In a multi-member repository, supply `--person-id` explicitly when creating events.

## Low-level CLI reference

The human-facing commands from the specifications are **prompt commands for the local AI agent**, not a requirement to implement seven shell subcommands. Their complete procedure lives in `AGENT_INSTRUCTIONS.md`.

| `groupctl` helper | Purpose |
|---|---|
| `init` | Create `.group/group.json`, the initial member descriptor, assignment placeholder, events/local/final folders, and local-state ignore rules. |
| `validate` | Validate group configuration, all member descriptors, local events, and any finalization records. |
| `events` | List local events; exits nonzero when invalid event files are found. |
| `event-create` | Create one immutable-format local JSON event from event-specific payload fields. Common envelope fields are added by `groupctl`. |
| `remote-events` | Inspect validated event blobs on fetched remote-tracking branches without changing branches or the working tree. |
| `final-candidate` | Generate `.group/final/candidate.md` and a `final_candidate` event from a JSON payload, while requiring the checked-out configured canonical branch and exact tip commit. |
| `finalize-confirmed` | After a human has reviewed and confirmed the candidate, generate `final_report.md`, `final.json`, and a `final_result` event. Requires `--human-confirmed`. |

### Example: create a local finding event

```powershell
python groupctl.py event-create --event-type finding --payload-file examples/finding_payload.json --person-id P17
python groupctl.py validate
python groupctl.py events
```

An event written locally is **not published** until it is committed and pushed. Published event files are immutable: correct errors by creating a new event related to the earlier one.

### Example: discover remote events

As part of `SYNC`, record branch/commit/status first, then fetch:

```powershell
git fetch --all --tags --prune
python groupctl.py remote-events --remote origin --new-only
```

After the agent has inspected and summarized all events successfully, it may checkpoint them locally:

```powershell
python groupctl.py remote-events --remote origin --mark-seen
```

The checkpoint is stored under `.group/local/` and is not committed. “Seen” means inspected, not accepted or integrated. Do not mark events seen if validation or immutability errors are reported.

## Finalization helpers

`FINAL` remains an AI-agent procedure. The helpers enforce mechanical checks, but the agent must first synchronize, find unintegrated published changes, inspect review/test/blocker evidence, and prepare a truthful candidate.

`final-candidate` expects a JSON payload with this shape (replace the sample commit with the current full 40-character canonical commit):

```json
{
  "canonical_branch": "main",
  "canonical_commit": "FULL_40_CHARACTER_COMMIT_SHA",
  "summary": "What the group produced.",
  "completed_work": ["Implemented and integrated feature X."],
  "contributors": ["P17 (Student A)", "P22 (Student B)"],
  "test_evidence": ["python -m unittest discover -s tests -v: pass on the specified commit"],
  "known_limitations": [],
  "unresolved_concerns": []
}
```

Save this in `.group/local/final_candidate_payload.json` and run:

```powershell
python groupctl.py final-candidate --payload-file .group/local/final_candidate_payload.json --person-id P17
```

Show `.group/final/candidate.md` to the human. Commit and push the candidate report and its `final_candidate` event. **Only after explicit human confirmation**, prepare `.group/local/final_payload.json` with `canonical_branch`, the candidate's full `canonical_commit`, `summary`, `completed_work`, `contributors`, `test_evidence`, `known_limitations`, and `status` (`completed` or `completed_with_known_limitations`). Then run:

```powershell
python groupctl.py finalize-confirmed --payload-file .group/local/final_payload.json --person-id P17 --human-confirmed --related-event <FINAL_CANDIDATE_EVENT_ID>
python groupctl.py validate
```

Commit and push `.group/final/final_report.md`, `.group/final/final.json`, and the created `final_result` event. The final code commit may be an ancestor of the branch tip when commits after it contain only `.group/` metadata records; the helper refuses to finalize if source/test files changed after the proposed code commit.

## Three-member demonstration

The demo creates a disposable local bare remote and three separate clones. It does not use your actual GitHub repository or modify this project folder.

Interactive run (the script asks you to type `FINALIZE` after showing the candidate):

```powershell
python scripts/run_three_member_demo.py
```

Fully scripted demonstration with an explicit simulated human confirmation:

```powershell
python scripts/run_three_member_demo.py --auto-confirm-final
```

The script demonstrates a clean integration, then deliberately introduces a conflict in `src/shared.py`, resolves it by combining both stated intents, runs tests, records integration/test events, integrates the accepted branch into the simulated `main`, and exercises finalization. The temporary demo repository is removed automatically when the script exits.

## Verification performed for this package

The package's test suite covers configuration/member validation, all documented event payloads, event creation and immutability, remote event discovery, invalid and conflicting remote events, final candidate creation, explicit confirmation, final report/JSON generation, and refusal when a candidate has unresolved concerns. The local three-member demo is also run end-to-end as a separate integration demonstration.

A local simulation is useful evidence but does **not** prove live GitHub authentication/permissions, simultaneous use by real students, or the quality of an independent AI agent's semantic judgement. Those still require the group to perform the assignment's live demonstration.
