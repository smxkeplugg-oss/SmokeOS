# CODING_STANDARD.md — How AIs Write Code in SmokeOS

## Principles

1. **Simplicity first.** Minimum code to solve the problem. No speculative features.
2. **Surgical changes.** Touch only what you must. Don't refactor working code.
3. **Match existing style.** Follow the patterns in surrounding files.
4. **Goal-driven.** Define success criteria before writing code.

## Python Conventions

- Python 3.12+ with type hints (`from __future__ import annotations`)
- Docstrings on all public functions/classes (Google style preferred)
- Atomic file writes: write `.tmp` → validate → `os.replace()`
- Use `pathlib.Path` over `os.path`
- Use `httpx` for async HTTP, `subprocess` for shell commands

## JavaScript/TypeScript (swarm_visor)

- React 18+ with TypeScript
- Vite for build
- Tailwind for styling
- ESLint + Prettier enforced

## Testing

- pytest for Python
- Every new feature needs at least one test
- Run: `python -m pytest tests/ -q --tb=short`
- Tests should pass BEFORE committing

## Git Conventions

- Branch naming: `feature/description`, `fix/description`, `foundation/description`
- Commit messages: `<type>: <brief description>`
- Types: `security`, `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- Never force-push to shared branches

## Security

- Never commit secrets (gitleaks pre-commit hook enforces)
- Never log API keys or tokens
- Never hardcode credentials — use env vars or config files (gitignored)
- Validate all inputs, especially CLI args and HTTP params

## AI-Specific Rules

- State assumptions explicitly before coding
- If multiple approaches exist, present them — don't pick silently
- If something is unclear, stop and ask
- After any architectural change, update .ai/DECISION_LOG.md

---
*Part of SmokeOS Governance Layer.*
