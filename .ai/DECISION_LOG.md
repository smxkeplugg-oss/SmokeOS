# DECISION_LOG.md — Architectural Decisions and Why

> Every architectural change must be logged here. Include: date, what changed, why, alternatives considered, and which AI made the decision.

## 2026-07-08 — AI Governance Layer Created

**What**: Split single PROGRAM.md into focused .ai/ directory files.
**Why**: A single 170-line file was too monolithic. AIs need targeted context (rules vs architecture vs coding style) without reading everything.
**Alternatives**: Keep PROGRAM.md as-is (rejected — too long, AIs skip it). Single YAML config (rejected — less readable for humans).
**Agent**: CodeBuff (Buffy)
**Confidence**: HIGH

## 2026-07-08 — SmokeOS Archaeologist Built

**What**: Created tools/archaeologist.py — scanner that indexes every SmokeOS-related file.
**Why**: 14,946 tracked files and unknown orphan files across the PC. Need full inventory before consolidation.
**Alternatives**: Manual grep (rejected — too slow, no dependency graph). Git-only scan (rejected — misses orphans outside repo).
**Agent**: CodeBuff (Buffy)
**Confidence**: HIGH

## 2026-07-08 — GitHub Remote Added

**What**: Pushed to https://github.com/smxkeplugg-oss/smokeos-local (private).
**Why**: Git as source of truth. Cloud AI Studio is reference plane, GitHub is canonical state.
**Agent**: CodeBuff (Buffy)
**Confidence**: HIGH

## 2026-07-07 — Security Sweep

**What**: Purged discord.json, .env, config/ai_keys.json, slack.json, and 10+ other secret files from all 85 commits via git filter-repo. Added gitleaks pre-commit hook.
**Why**: Discord bot token and API keys were committed to git history. Anyone cloning the repo could extract them.
**Agent**: CodeBuff (Buffy)
**Confidence**: HIGH

## 2026-07-07 — Cloud Sync Daemon

**What**: Created cloud_sync_v2.py — polls cloud deployment every 5min, detects drift via 3 tiers.
**Why**: Cloud (Google AI Studio) and local codebase diverge over time. Need automated drift detection.
**Agent**: CodeBuff (Buffy)
**Confidence**: MEDIUM (cloud is auth-protected, falls back to git comparison)

## Template

```
## YYYY-MM-DD — [Brief Title]

**What**: [One sentence description]
**Why**: [Why this decision was made]
**Alternatives**: [What else was considered and why rejected]
**Agent**: [Which AI made this decision]
**Confidence**: [HIGH/MEDIUM/LOW]
**Files affected**: [List of key files changed]
```

---
*Part of SmokeOS Governance Layer. Update this file after every significant change.*
