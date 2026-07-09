# AGENTS

**⚠️ Before making ANY edits, read the SmokeOS Governance Layer:**

**FIRST**: Read `ai_manifest.json` — machine-readable project map (version, ports, services, entrypoints, protected files, test locations, architecture hash).

**THEN** the human-readable docs:
1. `.ai/AI_RULES.md` — Immutable laws (12 rules every AI must follow)
2. `.ai/ARCHITECTURE.md` — System map, ports, directory layout
3. `.ai/DIRECTORY_RULES.md` — What you can and cannot touch
4. `.ai/CODING_STANDARD.md` — How to write code in this project
5. `.ai/ROADMAP.md` — Current priorities and known issues
6. `.ai/DECISION_LOG.md` — Why past decisions were made

**Run `python tools/smoke_doctor.py` FIRST — audit every SmokeOS folder on your machine.**
**Run `python tools/archaeologist.py` to understand the full project scope.**
**Run `python tools/manifest_generator.py --check` to verify manifest freshness.**

---

Use the `hive` CLI first.

- Canonical task state lives in `.hive/tasks/*.md`.
- Narrative project docs live in `projects/*/AGENCY.md`.
- `projects/*/PROGRAM.md` defines evaluator, path, and command policy.
- Run `hive context startup --project <project-id> --json` before autonomous edits.
- Run `hive sync projections --json` after canonical task or run changes.

<!-- hive:begin compatibility -->
## Hive 2.0 compatibility

1. Use the `hive` CLI first.
2. Prefer `--json` for machine-readable operations.
3. Treat `.hive/tasks/*.md` as canonical task state.
4. Read `projects/*/PROGRAM.md` before autonomous edits.
<!-- hive:end compatibility -->

## Tooling safety

**`str_replace` `allowMultiple=True` substring-safety rule:** when
applying multiple replacements in a single `str_replace` tool call
where the `replacements` array contains entries with
`allowMultiple=True`, assert that no replacement's source string is a
strict substring of any earlier replacement's target string.
Otherwise the multi-replace re-hits its own output (e.g.
``_SAFE_DIR → _SAFE_DIR_LEGACY → _SAFE_DIR_LEGACY_LEGACY``, the
subprocess-crashing ``NameError`` that landed in commit ``8eb104b`` and
went undetected through the prior 7-file pytest suite until
``python -m aiengine.audit.compressor`` was invoked post-commit).

Safer alternatives: (a) quote-anchor each individual rename by
disabling `allowMultiple`, (b) split the batch across multiple
`str_replace` calls where each call has a single `allowMultiple=False`
replacement, or (c) add a containment check in the calling code
before the chain, e.g.
``assert not target_str.startswith(source_str)``.
