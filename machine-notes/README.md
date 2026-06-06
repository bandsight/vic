# Machine Notes

This folder is the lightweight coordination layer for work done from more than one machine.

Use it for short, factual handoffs between Windows, Ubuntu/WSL, Codex, OpenClaw, and other automation runners.

## Format

Use this shape for new entries:

```markdown
## 2026-05-02 - machine-name - branch-name

Goal:

Commands run:

Result:

Blockers:

Next suggested action:
```

## Rules

- Do not paste API keys, auth tokens, `.env` contents, private customer material, source PDFs, or governed data dumps.
- Prefer command summaries over huge logs.
- Link to files or scripts when possible.
- If a command fails, include the exact command and the shortest useful error excerpt.
- If an agent changes code, mention the changed files.
