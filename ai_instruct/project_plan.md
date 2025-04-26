# x_violet Project Plan

## Purpose
A Twitter agent that mimics client-twitter and eliza, but uses the twikit API for all Twitter interactions (except auth/cookie creation, which is ported from client-twitter to Python). All requests go through a configurable SOCKS5 proxy with rotating IP support. Timeline actions and tweet/reply generation are handled by Google Gemini API, using persona from character.json. Media tweets use Gemini for image generation and persona alignment. Proxy status is shown at startup, and the user is prompted to refresh the IP if needed.

## Stack
- Python 3.10+
- twikit (Twitter API wrapper)
- proxystr (SOCKS5/rotating proxy)
- requests[socks] or httpx[socks]
- google-generativeai (Gemini API)
- Pillow/opencv-python (media)
- pytest/unittest (tests)

## Key Features
- Twitter agent via twikit (except auth/cookie creation)
- Persona-driven actions (character.json)
- LLM-driven timeline actions (Gemini)
- Media tweet generation (Gemini, persona-aligned)
- SOCKS5 proxy with rotating IP support
- Proxy status display and refresh prompt
- Modular, testable Python code

## Directory Structure
- ai_instruct/ (docs, features, tasks, agent_central)
- xviolet/ (core modules)
- tests/
- media/
- character/
- .env
- requirements.txt
- README.md

## Next Steps
- Research twikit-docs, client-twitter, proxystr, eliza
- Design config/env structure
- Scaffold codebase
- Implement proxy/auth logic
- Implement agent loop, LLM, media, tests
