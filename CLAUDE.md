# Claude Code - AI Engineer

**⚠️ Read the SmokeOS Governance Layer before touching any code:**

**FIRST**: Read `ai_manifest.json` — machine-readable project map (version, ports, services, entrypoints, protected files, test locations, architecture hash).

**THEN** the human-readable docs:
- `.ai/AI_RULES.md` (immutable laws)
- `.ai/ARCHITECTURE.md` (system map)
- `.ai/DIRECTORY_RULES.md` (permissions)
- `.ai/CODING_STANDARD.md` (style)
- `.ai/ROADMAP.md` (priorities)
- `.ai/DECISION_LOG.md` (past decisions)

Run `python tools/archaeologist.py` for a complete project inventory.
Run `python tools/manifest_generator.py --check` to verify manifest freshness.
Record all changes with `python tools/change_ledger.py record --what "..." --why "..." --agent claude`.

---

You are an AI coding assistant integrated with the SmokeOS autonomous system.

## Current Status

The system has a **Dream Mode** that runs when you're idle:
- After 15 seconds of inactivity, starts dreaming
- Dream status shown in terminal when you run OpenCode
- Check status: `type C:\Users\Quixk\aiengine\.dream_status.json`

## Available Skills

- `loop` - Run prompts infinitely
- `dream` - Enter dream mode (autonomous when idle)
- `continuous_optimizer` - Continuous optimization

## PM2 Processes Running

- `dream-skill` - Dreams when you're idle
- `loop-skill` - Runs infinite loops
- `auto-improve` - Self-improves
- `discord-bridge` - Discord integration
- `smokeos-kernel` - API server (port 3421)

## Quick Commands

- `pm2 list` - Show all processes
- `pm2 logs dream-skill` - Watch dreams
- `type .dream_status.json` - Check dream status
