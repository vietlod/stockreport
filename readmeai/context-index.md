# Context Index — AI Governance Navigation Map

This document is the central index mapping typical development and AI tasks to the appropriate governance documents and terminal compression policies.

---

## 1. Quick Orientation

Before reading any deep configuration or logic, read this index to locate the relevant files.

```
[Start Session] ──> CLAUDE.md ──> Memory.md ──> context-index.md ──> Target Doc
```

---

## 2. Task-to-Document Mapping

| Category | Specific Task | Target Document | Secondary Reference |
|---|---|---|---|
| **Architecture** | Understand components & stack | [architecture-map.md](file:///d:/FLOW/Crawl/readmeai/architecture-map.md) | [service-boundaries.md](file:///d:/FLOW/Crawl/readmeai/service-boundaries.md) |
| | Check critical files & source code | [file-criticality-map.md](file:///d:/FLOW/Crawl/readmeai/file-criticality-map.md) | |
| **Infrastructure**| Check VPS co-tenant ports & paths | [vps-app-context.md](file:///d:/FLOW/Crawl/readmeai/vps-app-context.md) | [docker-map.md](file:///d:/FLOW/Crawl/readmeai/docker-map.md) |
| | Verify build/run commands | [build-runbook.md](file:///d:/FLOW/Crawl/readmeai/build-runbook.md) | |
| | Deploy updates or do releases | [deploy-checklist.md](file:///d:/FLOW/Crawl/readmeai/deploy-checklist.md) | |
| **Troubleshoot** | Investigate a bug / trace logs | [debug-playbook.md](file:///d:/FLOW/Crawl/readmeai/debug-playbook.md) | [decision-log.md](file:///d:/FLOW/Crawl/readmeai/decision-log.md) |
| | Test logic / verify contract | [testing-strategy.md](file:///d:/FLOW/Crawl/readmeai/testing-strategy.md) | |

---

## 3. Terminal Output Compression Guidelines (RTK)

For terminal-output heavy tasks, consult [RTK.md](file:///d:/FLOW/Crawl/RTK.md) and apply these constraints:

| Task Type | Target Doc | Command / RTK Filter | Raw Output Escalation Criteria |
|---|---|---|---|
| **Repo Exploration**| [context-index.md](file:///d:/FLOW/Crawl/readmeai/context-index.md) | `git status -s` / `Get-ChildItem -Name` | Only when file metadata or structure is suspect. |
| **Git Review** | [context-index.md](file:///d:/FLOW/Crawl/readmeai/context-index.md) | `git diff --stat` | When verifying specific line modifications or security patches. |
| **Build & Run** | [build-runbook.md](file:///d:/FLOW/Crawl/readmeai/build-runbook.md) | `pip install -q` | When a build failure occurs and full compiler warnings/errors are needed. |
| **Testing** | [testing-strategy.md](file:///d:/FLOW/Crawl/readmeai/testing-strategy.md) | Custom script checks | When a test fails and the full assertion stack trace is needed. |
| **Logs Check** | [debug-playbook.md](file:///d:/FLOW/Crawl/readmeai/debug-playbook.md) | `journalctl -n 50 --no-pager` | When investigating request flows using correlation IDs or timestamps. |
