# AI_RULES.md — Immutable Laws for Any AI

> **⚠️ READ FIRST. Every AI. Every session. No exceptions.**
> Applies to Claude, Gemini, CodeBuff, Cursor, Cline, OpenCode, Goose, Windsurf, Continue.

## Immutable Laws

1. **NEVER push to master/main directly.** Branch → PR → human approval only.
2. **NEVER merge your own PR.** Only a human clicks Merge.
3. **NEVER modify files in READ ONLY directories.** Read for context, do not edit.
4. **NEVER delete files unless instructed.** Rename or archive instead.
5. **NEVER auto-execute trades.** Trader requires human `--live` flag.
6. **NEVER bypass guardrails.** `guardrails.py` runs BEFORE any trade.
7. **NEVER commit secrets.** Gitleaks pre-commit hook enforces this.
8. **NEVER modify .gitignore to unhide secrets.** It is the last line of defense.
9. **NEVER kill another process port.** Report conflicts. Do not `taskkill`.
10. **ALWAYS write .tmp → validate → os.replace()** for atomic file writes.
11. **ALWAYS run pytest** after changes to backend/, SmokeOS/, or smokeos_local/.
12. **ALWAYS update .ai/DECISION_LOG.md** after any architectural change.

## Kill Switch

- **Trigger**: Touch `.smokeos_state/kill_switch.flag`
- **Reset**: Delete that file
- **CLI**: `python SmokeOS/guardrails.py --kill "reason"`
- **Phone**: `/api/v1/kill` via phone gateway (:3440)

The kill switch is ABSOLUTE. Halt all trading immediately.

## Pipeline (every change must pass)

```
1. Does it import?  → python -c "import <module>"
2. Do tests pass?   → python -m pytest tests/ -q --tb=short
3. Gitleaks clean?  → gitleaks git --staged
4. Code review      → human approval required
5. Merge            → human merges PR
```

**The pipeline decides. You don't.**

---
*Part of SmokeOS Governance Layer. See also: ARCHITECTURE.md, DIRECTORY_RULES.md, CODING_STANDARD.md*
