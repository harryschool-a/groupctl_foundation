# Local AI Agent Collaboration Instructions — Version 0.1

This file defines how the local AI coding agent responds when the human uses the collaboration prompt commands. These are **human-to-agent prompt commands**, not seven required shell subcommands. Use Git for version-control facts and `groupctl` for deterministic repository/event operations. Use reasoning for semantic compatibility and conflict decisions. Ask the human when the correct behavior is materially uncertain.

## Global rules

1. Start in the repository root. Read `.group/group.json`; `canonical_branch` is authoritative. Do not assume `main` if the configuration specifies another branch.
2. Use `.group/members/<person_id>.json` to establish the current configured identity. Personal work branches follow `people/<person_id>/<topic>`.
3. Run `python groupctl.py validate` when relevant. Do not treat an invalid event as a valid protocol record.
4. The actual Git diff and commit history are authoritative for code changes. An event summary is context, not proof. Verify referenced commits and run relevant checks when practical.
5. Events under `.group/events/<event_id>.json` are immutable after publication. If information must change, create a new related event; do not edit a published event.
6. Never force-push, discard uncommitted work, reset the canonical branch, overwrite tests just to make checks pass, or resolve a conflict by arbitrarily choosing a side. Preserve work and ask the human when needed.
7. Keep private chat and experimental reasoning private. Publish only useful engineering information through the repository.
8. `.group/local/` is for local-only support state. Do not commit its contents except the required `.group/local/.gitkeep`.
9. Do not report a Git operation or test as successful unless the tool output/history confirms it.

## `SYNC` — synchronize working context with the group

1. Record the current branch (`git branch --show-current`), current commit (`git rev-parse HEAD`), and working-tree state (`git status --short`). Inspect tracked changes and untracked files. Do not discard or overwrite them.
2. Fetch remote refs and tags without changing the checked-out branch: `git fetch --all --tags --prune`. If fetch fails, report the error and do not claim the group is synchronized.
3. Discover events on fetched remote branches, not only files in the current checkout: run `python groupctl.py remote-events --remote origin --new-only` for `origin`, or use the relevant named remote. Read each newly discovered event and its referenced code/commit. If the command reports an invalid event or immutability conflict, report it and do not checkpoint it as successfully inspected.
4. Compare the current working branch with the remote-tracking canonical branch named by `.group/group.json`. Verify that the corresponding `origin/<canonical_branch>` ref exists. Inspect the ahead/behind relationship and local changes.
5. Incorporate canonical updates into the current work branch only when safe and in line with repository policy. Protect dirty work first. If no policy specifies merge versus rebase, prefer a non-destructive merge; do not blindly run `git pull`, reset the branch, or force-push. Do not automatically merge unrelated feature branches.
6. Inspect relevant `change_published`, `review`, `integration_result`, `test_result`, `finding`, `question`, `answer`, and `blocker` events. Check important claims against real commits/diffs and test output.
7. If synchronization changed code, run quick relevant validation. Then summarize: current branch/commit, canonical commit, newly discovered events, what was incorporated, what remains separate, failures/blockers, and any assumptions that need revision.
8. After all discovered events have been inspected and summarized, record the local discovery checkpoint with `python groupctl.py remote-events --remote origin --mark-seen`. This checkpoint means “inspected,” not “accepted” or “integrated.” Do not mark events seen if the event listing reported validation or immutability errors.

A clean pull by itself is not a complete SYNC.

## `PUB` — publish a coherent contribution

1. Inspect branch, status, staged/unstaged diffs, untracked files, and recent commits. If the current branch is the configured canonical branch, stop and ask the human before publishing source changes; publish a personal branch instead.
2. Confirm the branch follows `people/<person_id>/<topic>`. If identity or branch ownership is unclear, ask before publishing.
3. Determine which changes form one coherent contribution. Inspect all diffs; stage only relevant files, not every file blindly. Check for secrets, credentials, generated junk, unexpected files, conflict markers, and accidental unrelated edits. Run appropriate quick tests/build checks.
4. Review the staged diff with `git diff --cached` and run `git diff --cached --check`. If the work is not ready, explain the concrete issue rather than claiming success.
5. Commit coherent source changes with a meaningful message and push the personal branch. Do not force-push. If push is rejected, fetch and reconcile safely or ask the human.
6. Record the pushed code commit (full SHA), branch name, changed files, interface/assumption changes, tests run, known issues, and whether integration is proposed. Choose a unique `change_id` that is not already used by a `change_published` event; follow any established repository convention, otherwise use `C-<short-commit-sha>` and verify uniqueness.
7. Create a payload containing the documented `change_published` fields: `change_id`, `branch`, `commit`, `summary`, `files_changed` (string array), `interface_changes` (string array), `tests_run` (string array), `known_issues` (string array), and `proposed_for_integration` (boolean). Do not provide common envelope fields; `groupctl` adds them.
8. Save the payload temporarily under `.group/local/` and run, for example: `python groupctl.py event-create --event-type change_published --payload-file .group/local/change_published_payload.json --person-id <person_id>`. Validate with `python groupctl.py validate`.
9. Stage only the new `.group/events/<event_id>.json`, commit the event separately, and push the same personal branch. The event's `commit` must identify the code commit, not the later event-only commit. This makes the event discoverable from the fetched remote branch.
10. Report the `change_id`, code commit, branch, tests/known limitations, event ID, and whether both branch and event were pushed. Never say PUB succeeded unless both pushes/commits succeeded.

## `REV <change_id>` — review without merging

1. Fetch as needed and locate the `change_published` event for the exact change ID, including events on fetched remote branches.
2. Confirm the referenced branch and commit exist. Inspect the actual diff and surrounding code, declared interface/assumption changes, tests, regressions, edge cases, complexity, and compatibility with canonical code.
3. Run relevant tests when practical. Separate definite defects, plausible risks, missing evidence, and subjective preferences.
4. Choose exactly one verdict: `accept`, `accept_with_changes`, `reject`, or `needs_more_evidence`.
5. Create a `review` event containing `change_id`, `verdict`, `summary`, `issues` (string array), and `tests_run` (string array). Validate, then commit and push the event. A positive review does not merge the change.

## `INT <change_id>` — integrate a specific published change

1. Perform the discovery parts of SYNC and locate the matching `change_published` event. Confirm its branch and commit exist.
2. Inspect the actual diff, declared interface changes, surrounding code, and the target branch. The target is the current working branch unless the human or repository policy specifies otherwise; do not silently target the canonical branch.
3. Preserve uncommitted work before integration. Merge/rebase using repository policy. If a conflict occurs, inspect both sides and understand both intents. Resolve only when the intended combined behavior is clear; otherwise stop, preserve the conflict state safely, and publish a `blocker` requesting a human decision.
4. Verify that the referenced commit is incorporated; check leftover conflict markers; build if applicable; run relevant tests; and perform semantic compatibility review. A conflict-free Git merge alone is not success.
5. Publish an `integration_result` containing `change_id`, `target_branch`, `result` (`success`, `failed`, or `needs_human`), `merge_commit` for successful integration, `conflicts` (string array), `conflict_resolution_summary` when relevant, `verification` (mapping check names to string results), and `summary`.
6. Commit/push the event and report what happened. Integration into a personal branch does not mean the change is in canonical state.

## `TEST [scope]` — produce test evidence

1. Resolve the requested scope: current branch by default; configured canonical branch when requested; or a named published change when a change ID is supplied. Identify and record the exact commit SHA before testing.
2. Discover available tests/build/lint/static-analysis checks from repository configuration and instructions. Run applicable checks. Do not edit expected outputs only to make tests pass.
3. Investigate failures enough to distinguish product failure, stale/broken tests, missing environment, and inconclusive results. Identify concrete manual checks where automation is insufficient.
4. Publish a `test_result` event containing `scope`, `commit`, `commands` (string array), `automated_result` (`pass`, `fail`, `partial`, or `not_available`), non-negative integer `passed`, `failed`, and `skipped`, `human_checks_required` (string array), and `summary`.
5. Report what is proven, what failed, and what remains unknown. The result applies only to the exact commit tested.

## `STATUS` — report current group position

1. Inspect current branch, commit, working tree, configured canonical branch/commit, and ahead/behind relationship. Fetch remote metadata first when appropriate and safe.
2. Validate local events and inspect relevant remote events. Report uncommitted work, published changes, unintegrated changes, latest review/test evidence, blockers, and the last tested commit where known.
3. Recommend one concise next action. STATUS itself should not perform a large merge or rewrite code.

## `FINAL` — finalize one group result

1. Synchronize metadata and canonical state. Read `canonical_branch` from `.group/group.json` and identify the exact proposed canonical commit SHA.
2. Enumerate every published `change_published` event and determine which referenced commits are incorporated into the canonical commit. Investigate unincorporated changes: intentionally rejected/obsolete, still important, or unknown. Do not treat a personal-branch test as evidence that the same code is canonical.
3. Review latest review, test, integration, and blocker events. Run final automated checks on the exact proposed canonical commit when feasible; identify required human checks and known limitations.
4. If important work, failing checks, or significant blockers remain unresolved, stop short of claiming completion. Explain the issue and prepare an honest candidate with unresolved concerns.
5. Generate `.group/final/candidate.md` with completed work, canonical branch and exact commit, contributions, validation evidence, known limitations, and unresolved concerns. Show it to the initiating human and request confirmation. Do not skip this confirmation.
6. Only after human confirmation, create `.group/final/final_report.md` and `.group/final/final.json`, and create a `final_result` event that identifies the canonical commit, report path, test evidence, known limitations, and initiating person. A `final_candidate` event may be used to record the proposal before confirmation.
7. Validate the event/repository, commit and push finalization records, and report the canonical commit and report path. Finalization records must not imply that unresolved failures were passed.

`FINAL` means group finalization, not submission of the initiator's personal branch.
