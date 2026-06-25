# RTK.md — Terminal Output Compression Policy

This document defines the standard terminal output compression policy for all AI coding assistants (Claude Code, Cursor, Codex, Copilot, Gemini CLI, AntiGravity) working on the Stock Report repository.

---

## 1. Core Objectives
- **Reduce Token Overhead:** Truncate, filter, and summarize verbose CLI outputs to prevent context pollution and lower token consumption by 60-90%.
- **Minimize Noise:** Strip routine logs, progress bars, and duplicate warnings, retaining only diagnostic data, errors, and actionable results.

---

## 2. Default Compression Rules

By default, agents **MUST** route common commands through the following compression wrappers or filters:

| Command Category | Raw Command | Recommended RTK / Filter Pattern | Compression Target |
|---|---|---|---|
| **Dependency Install**| `pip install -r req.txt` | `pip install -q -r req.txt` | Hide progress logs and successful packages. |
| **Git Review** | `git status` | `git status -s` | Hide verbose staging hints. |
| | `git diff` | `git diff --stat` | Review changes by file size first before reading code diffs. |
| **Scraper Run** | `python scraper.py` | `python scraper.py \| grep -E "Error\|Failed\|Scraped"` | Suppress continuous progress lines from Playwright. |
| **Server Health** | `journalctl -u stockreport`| `journalctl -u stockreport -n 50 --no-pager` | Limit log lines to recent status context. |
| **File Tree** | `Get-ChildItem -Recurse`| `Get-ChildItem -Name` | Avoid printing deeply nested file lists. |

---

## 3. Escalation to Raw Output Criteria

An agent may request or print raw terminal output **only** under the following conditions:
1. **Compilation/Build Failures:** When a syntax or import error occurs and the full compiler stack trace is required to resolve it.
2. **Traceback Analysis:** When an exception occurs during runtime and the complete stack trace is necessary.
3. **API Contract Verification:** When validating the exact JSON structure returned by a backend route or Google OAuth response.
4. **Security / Forensics:** When auditing exact line diffs for commit compliance.

---

## 4. Fallback Strategy (When Compression Tooling is Unavailable)

If an automated command wrapper (like the `rtk` utility) is not installed on the system:
- **Pre-filtering:** The agent must pipe commands to filters (e.g. `grep`, `head -n N`, `Out-String` in PowerShell).
- **Manual Summarization:** When copying output into the AI context, the agent must manually strip progress bars, duplicate logs, and success chatter. Only copy the command, exit code, and failure stack traces.

---

## 5. Tool-Specific Integration Notes

- **Claude Code:** Use shell commands sparingly. Prioritize built-in file view/search operations which do not write to the terminal history.
- **Cursor / Copilot / Gemini CLI:** When copying logs into the chat context, only include the relevant slice of errors rather than dumping the full terminal history.
- **AntiGravity:** Maintain this compression policy when scheduling tasks, running tests, or logging VPS operations.
