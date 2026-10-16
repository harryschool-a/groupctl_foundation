## 3. REV (Review)
**Trigger:** User types `REV <change_id>`
**Procedure:**
1. Analyze the proposed change identified by `<change_id>`.
2. Generate a valid JSON payload for a `review` event. It must include `change_id`, a `verdict` (must be one of: accept, accept_with_changes, reject, needs_more_evidence), and a `summary`.
3. Save this payload to a temporary file (e.g., `local_review.json`).
4. Run `python groupctl.py event-create --event-type review --payload-file local_review.json`.
5. Execute the `PUB` workflow to automatically commit and push the new review event.

## 4. INT (Integration)
**Trigger:** User types `INT <change_id>`
**Procedure:**
1. Attempt to integrate the change identified by `<change_id>` into the target branch.
2. Generate a valid JSON payload for an `integration_result` event. It must include `change_id`, `target_branch`, a `result` (must be one of: success, failed, needs_human), a `summary`, and a `verification` dictionary.
3. Save this payload to a temporary file (e.g., `local_integration.json`).
4. Run `python groupctl.py event-create --event-type integration_result --payload-file local_integration.json`.
5. Execute the `PUB` workflow to automatically commit and push the new integration event.
## 5. TEST (Test)
**Trigger:** User types `TEST` or `TEST <scope>`
**Procedure:**
1. Run the local test suite for the specified scope.
2. Generate a valid JSON payload for a `test_result` event. It must include `scope`, `commit`, `automated_result` (must be: pass, fail, partial, or not_available), a `summary`, and integer counts for `passed`, `failed`, and `skipped`.
3. Save this payload to a temporary file (e.g., `local_test.json`).
4. Run `python groupctl.py event-create --event-type test_result --payload-file local_test.json`.
5. Execute the `PUB` workflow to automatically commit and push the test event.

## 6. STATUS (Status)
**Trigger:** User types exactly `STATUS`
**Procedure:**
1. Run `git status` to check for uncommitted files.
2. Run `python groupctl.py validate` to check the group configuration.
3. Run `python groupctl.py events` to list all known collaboration events.
4. Provide a summarized report of the repository health, pending changes, and collaboration events to the user.
## 7. FINAL (Finalization)
**Trigger:** User types `FINAL <canonical_commit>` or exactly `FINAL`
**Procedure:**
1. Determine the intent: if `<canonical_commit>` is provided, the user is proposing a final version. If not, the user is submitting a final approval result.
2. Generate a valid JSON payload for either a `final_candidate` or `final_result` event based on the intent. Both must include `canonical_commit` and a `summary`.
3. Save this payload to a temporary file (e.g., `local_final.json`).
4. Run `python groupctl.py event-create --event-type final_candidate` (or `final_result`) `--payload-file local_final.json`.
5. Execute the `PUB` workflow to automatically commit and push the final event.