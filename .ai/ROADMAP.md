# ROADMAP.md — Current Priorities and Next Steps

> **Last updated**: 2026-07-08
> **Active branch**: foundation/smokeos-governance

## Phase 1: Foundation (CURRENT)

- [x] Create foundation branch
- [x] Build SmokeOS Archaeologist
- [ ] Build AI Governance Layer (.ai/ directory)
- [ ] Set up GitHub CI/CD
- [ ] Build AI Change Ledger
- [ ] Wire AGENTS.md to auto-load .ai/

## Phase 2: Consolidation

- [ ] Run Archaeologist full scan
- [ ] Merge SmokeOS/ + smokeos_local/ into unified directory
- [ ] Purge large log files from git history
- [ ] Standardize config into single source of truth
- [ ] Enable branch protection on GitHub

## Phase 3: Enterprise Hardening

- [ ] SmokeOS Brain (indexed knowledge graph)
- [ ] CI/CD pipeline (pytest, lint, security scan on every PR)
- [ ] Secrets rotation (move from plaintext to vault)
- [ ] Standardized health endpoints on all services
- [ ] Disaster recovery documentation

## Known Issues

- 14,946 tracked files — need consolidation
- 50MB+ log files in git (claude_execution.log, compressor.log)
- 152 orphan files found by Archaeologist
- Two competing kernel/API systems (SmokeOS/ vs smokeos_local/)
- No CI/CD pipeline
- No branch protection on GitHub

## Quick Wins

1. Enable branch protection (30 seconds in GitHub Settings)
2. Add `SmokeOS/logs/` to .gitignore
3. Run Archaeologist --full for complete inventory
4. Create CODEOWNERS

---
*Part of SmokeOS Governance Layer.*
