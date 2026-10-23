# Final Package Validation Notes

This note records the checks performed on the packaged version of `groupctl`.

- `python -m unittest discover -s tests -v`: passed (27 tests).
- `python tests/test_groupctl.py`: passed (27 tests).
- `python scripts/run_three_member_demo.py --auto-confirm-final`: passed end-to-end using a temporary bare Git remote and three local clones.
- The demo observed `remote-events` discovery on personal branches, one clean merge, one deliberately generated conflict in `src/shared.py`, a chosen conflict resolution preserving both intents, passing post-merge tests, `integration_result` and `test_result` events, canonical integration, and final candidate/finalization records.
- The demo ended with `groupctl validate` reporting configuration, events, members, and final records as valid.

## Scope limitation

This is a local deterministic simulation. It does not demonstrate live GitHub authentication, actual concurrent collaboration by three real students, or that a specific AI vendor resolves arbitrary semantic conflicts correctly. The portable agent instructions define the judgment workflow; those human/AI judgments must still be exercised in a live group demonstration.
