# groupctl foundation — Version 0.1

This project is a collaboration helper for several human–AI pairs working in one programming group. It is not the Dispatcher and is not a complete autonomous multi-agent system.

## Implemented local helper features

- `init`: create the required `.group/` scaffold, group configuration, member descriptor, and placeholder assignment file.
- `validate`: validate group configuration and local event common envelopes plus the documented event payload fields.
- `events`: list and validate event files in the current checkout.
- `event-create`: create a local event from a JSON payload file, adding the common envelope from `.group/group.json` and `.group/members/`.
- `remote-events`: after a Git fetch, inspect event files on fetched remote-tracking branches without checking out those branches or modifying the working tree. Detect malformed events and event-ID content conflicts. An optional local-only checkpoint helps SYNC distinguish events already inspected from newly discovered ones.
- Unit tests for configuration, event validation/creation, immutable event writes, and remote event discovery using a local Git remote.

These are low-level implementation helpers. `SYNC`, `PUB`, `INT`, `REV`, `TEST`, `STATUS`, and `FINAL` are human-to-agent prompt commands whose procedures are defined in [`AGENT_INSTRUCTIONS.md`](AGENT_INSTRUCTIONS.md). Do not present them as required shell subcommands.

## Windows setup

Open Command Prompt or PowerShell in the folder that contains `groupctl.py`.

```cmd
python -m unittest discover -s tests -v
python groupctl.py init --group-id G-12 --person-id P17 --display-name "Student A"
python groupctl.py validate
python groupctl.py events
```

Run `init` only once in a repository. If `.group/group.json` already exists, skip `init`.

## Create a local event

```cmd
python groupctl.py event-create --event-type finding --payload-file examples/finding_payload.json
python groupctl.py validate
python groupctl.py events
```

When exactly one member descriptor exists, `groupctl` infers the person ID. In a multi-member repository, supply `--person-id P17` explicitly. For related events, add `--related-event EVENT_ID`; repeat the option if there are multiple related events.

An event created on disk is **not yet published**. The repository contract says it becomes public only after it is staged, committed, and pushed with Git.

## Discover events on fetched remote branches

First record local branch/commit/working-tree state and then fetch, as part of the SYNC procedure:

```cmd
git fetch --all --tags --prune
python groupctl.py remote-events --remote origin --new-only
```

This command is read-only unless `--mark-seen` is explicitly supplied. It inspects remote-tracking refs such as `origin/people/P17/parser`, so events on a teammate's personal branch can be discovered before their code is merged into the current branch.

After the agent has inspected and summarized all reported events, it may update the local-only checkpoint:

```cmd
python groupctl.py remote-events --remote origin --mark-seen
```

The checkpoint is stored under `.group/local/` and is not shared or committed. “Seen” means inspected, not accepted or integrated. Do not checkpoint when the command reports invalid events or immutability conflicts. If your remote is not named `origin`, replace it with the actual remote name.

## Important boundaries

- `.group/group.json` identifies the canonical branch. Do not assume `main` if the configuration differs.
- Published events are immutable. Correct mistakes with a new related event.
- `remote-events` reads already-fetched references; it does not run `git fetch` itself and does not change branches.
- This milestone improves event discovery and agent procedures. It does **not** yet automate the complete `PUB`, `INT`, `REV`, `TEST`, `STATUS`, or `FINAL` workflows end-to-end.
