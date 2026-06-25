---
name: repo-governance
description: Enforce AI governance, context loading hierarchy, and terminal output compression disciplines on the Stock Report repository.
---

# Repository Governance Skill

This skill enforces strict repo-level governance, multi-app VPS safety measures, and context-token optimization via terminal output compression (RTK).

---

## 1. Initial Engagement Sequence

Whenever this skill is triggered, you **MUST** follow this initial context orientation sequence:
1. Load `CLAUDE.md` to load the current session workflow constraints.
2. Load `Memory.md` to synchronize active learnings and past actions (such as domain migration).
3. Load `Agents.md` to define and map your active role (e.g. Planner vs. Implementer).
4. Load `readmeai/context-index.md` to map target files.

---

## 2. Plan Mode Disciplines

Before modifying any source code:
- Draft a **Working Summary** capturing the task, targets, and unknowns.
- Write or update `implementation_plan.md`.
- Ensure no shared infrastructure (Nginx configurations, ports, other VPS docker containers) is modified without explicit user approval.
- Seek approval from the user before executing changes.

---

## 3. Terminal Compression Rules (RTK)

To preserve tokens during terminal execution:
- Pipe verbose output to summaries or grep filters where possible.
- Default to `rtk <cmd>` for common command runs (like `git diff`, `npm install`, `docker ps`).
- Compress progress bars and routine logs; keep only failures, exit codes, and relevant stack traces.
