# Agent Briefing: x_violet Project

## Welcome, Agent!

This document provides the necessary context to contribute to the `x_violet` Twitter agent project.

## Project Goal

To create a Python-based Twitter agent named `x_violet` that:
- Mimics the behavior and persona handling of `eliza` and `client-twitter`.
- Uses the `twikit` library for all Twitter API interactions (except initial auth).
- Uses a Python port of `client-twitter`'s logic for initial authentication and cookie saving.
- Strictly routes **all** network traffic through a configurable SOCKS5 proxy (with rotating IP support).
- Leverages Google Gemini API for timeline action decisions, tweet/reply generation, and media context analysis/generation.
- Operates based on a persona defined in `character/holly.json`.
- Manages media uploads and interactions.

## Tech Stack

- **Language:** Python 3.10+
- **Core Libraries:**
    - `twikit`: Twitter API interaction (via `twiki-docs.md`)
    - `proxystr`: SOCKS5/rotating proxy handling (based on `libs & docs/proxystr`)
    - `requests[socks]` / `httpx[socks]`: Proxied HTTP requests
    - `google-generativeai`: Google Gemini API client
    - `Pillow` / `opencv-python`: Image/media handling
    - `python-dotenv`: Environment variable management
    - `pytest` / `unittest`: Testing
- **Configuration:** `.env` file, `character/holly.json`
- **Cookies:** `xviolet/client/cookies.json`

## Key Reference Documents & Codebases

*   **This Project:**
    *   `ai_instruct/project_plan.md`: Detailed plan and structure.
    *   `ai_instruct/features.md`: Feature checklist.
    *   `ai_instruct/tasks.md`: Task breakdown.
    *   `ai_instruct/updates.md`: **CRITICAL - Collaboration log and task delegation.**
    *   `character/holly.json`: Agent persona definition.
*   **External References (Located in `/root/workspace/libs & docs` or `/root/workspace/eliza`):**
    *   `twiki-docs.md`: Essential documentation for using the `twikit` library.
    *   `client-twitter` (JS/TS): Source for authentication/cookie logic to be ported to Python.
    *   `proxystr` (Python): Source for SOCKS5/rotating proxy implementation patterns.
    *   `twkit_ext` (Python): Example usage of `twikit` with proxies.
    *   `eliza` (JS/TS): Reference for persona processing, LLM integration, and agent action patterns.

## Collaboration Protocol (IMPORTANT)

1.  **Check `ai_instruct/updates.md` First:** Before starting any work, review the latest updates and delegations in this file.
2.  **Log Your Work:** Record all significant actions, code completions, research findings, and decisions in `ai_instruct/updates.md`. Use the format: `[Timestamp] - [Action/Update Description] - [Your Agent Name]`.
3.  **Acknowledge Delegations:** If a task is delegated to you, acknowledge it in the log.
4.  **Delegate Clearly:** If you need to delegate tasks, add them to the 'Delegations' section in `updates.md`, specifying the target agent.
5.  **Ask Questions:** If blocked or unsure, log your question in `updates.md` directed at another agent (e.g., `@Cascade: [Question]`).

## Current Task Distribution

Refer to the 'Delegations' section in `ai_instruct/updates.md` for the current task assignments between Cascade and Augment.

---

*Good luck, and let's build an amazing agent!*
