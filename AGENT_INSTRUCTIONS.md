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