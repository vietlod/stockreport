# CLAUDE.md — AI Governance & Development Workflow

This document defines the strict development workflow, safety rules, and context/terminal compression disciplines for any AI agent interacting with the Stock Report repository on the shared production VPS.

---

## 1. AI Governance & Priority Order

To minimize token cost and prevent cross-app impacts on the shared VPS, you **MUST** load context in the following priority order:
1. `CLAUDE.md` (This file — Agent execution rules)
2. `Memory.md` (Active session state & learnings)
3. `Agents.md` (Multi-agent roles & handoffs)
4. `readmeai/context-index.md` (Index of governance files)
5. Only the specific `readmeai/` files directly relevant to the current task.

> [!IMPORTANT]
> **Task-Scoped Reading:** Do NOT scan the entire repository or read unneeded documents. Use `context-index.md` to pinpoint target files.

---

## 2. Planning & Verification Workflow

### Phase A: Orientation & Research
- Create a brief **Working Summary** before any code changes:
  - Task Summary
  - Likely Affected Files
  - Likely Affected Services/Processes (e.g. systemd stockreport service, nginx)
  - Unknowns
- Research the codebase to locate files, but do NOT execute modifying commands.

### Phase B: Implementation Plan (Plan Mode)
- Every non-trivial change **requires** an implementation plan in `implementation_plan.md` (or equivalent artifact depending on the agent interface).
- Identify risks, dependencies, and rollback scenarios.
- Request user review and wait for **explicit approval** before coding.

### Phase C: Implementation (Code Mode)
- Execute changes precisely following the approved plan.
- Maintain existing codebase comments and docstrings.
- Adhere strictly to the **Git Commit Rules** (see §5).

### Phase D: Verification & Documentation
- Perform tests on the VPS (checking systemd services, web pages, or logs).
- Document changes in a walkthrough.
- Update `Memory.md` and related governance documents.

---

## 3. Ask-User Rules (Strict Input/Context Safeguards)

If crucial context (infrastructure, credentials, or target behavior) is missing, you **MUST** ask the user at least **5 Core Questions** before proceeding. These questions must cover:
1. **Business Goal**: The primary business outcome.
2. **Expected Behavior**: Detailed end-user experience or API responses.
3. **Scope & Non-Goals**: What is explicitly excluded.
4. **Infra & Deploy Constraints**: Ports, systemd services, docker settings, databases, or domains.
5. **Definition of Done**: Clear criteria for success and validation.

**Exception:** You may bypass this rule only if the task is trivial, fully specified, has zero risk of production/security regression, and does not alter database schemas, public APIs, or Nginx/systemd configurations.

---

## 4. Terminal Output Compression (RTK Policy)

Raw terminal output is expensive and noisy. You **MUST** prioritize compressed and summarized terminal logs:
- **Default:** Run command via `rtk <cmd>` (or summary wrapper) to filter progress bars, repeated logs, and build noise.
- **Manual Summary:** If no automated tool is active, summarize the terminal output manually before inserting it into the AI context. Only keep errors, critical warnings, exit codes, and durations.
- **Escalation to Raw:** You may request raw terminal output *only* for deep stack trace analysis, compliance checks, forensic logs, or API contract validation when a summary is insufficient.

---

## 5. Git Commit Rules

- **Never** add `Co-authored-by` or `Co-Author By` trailers.
- **Never** add AI signatures, credit lines, model names, or generated-by claims.
- **No Apology/Disclaimer Text**: Commit messages, PR descriptions, and comments must be strictly technical and concise.
- Output only the requested commit title/body without marketing noise.
