# Run 5 notes: SSO, AI connectors, PI dashboard, training, data management

The founder asked for detailed notes of everything done, every issue hit and every design choice. Each agent appends its own section below. Decisions also go in `docs/DECISIONS.md` under "Run 5".

## Orchestrator: scope and the AI question (2026-11-05)

- **Can users plug in their Claude Pro or ChatGPT Plus subscription?** Not into our app. Consumer subscriptions work only inside claude.ai or chatgpt.com, and API access is billed separately. What does work is the reverse: we expose the lab app as a **remote MCP server**, and the user adds it as a custom connector in their own Claude (Pro, Max, Team or Enterprise). Their subscription then pays for the AI, and our app only answers permission-checked tool calls. ChatGPT supports MCP connectors on some plans; the MCP agent checks the details.
- **Second path:** an in-app assistant where each user pastes their own Anthropic or OpenAI **API key** (pay as you go, encrypted at rest like integration keys).
- **Shared tool layer:** both paths use one set of permission-scoped tools, so the AI can never see more than the user can.
- **Waves:**
  - Wave 1: SSO (opus), MCP server and tool layer (opus), PI dashboard (sonnet), training and certifications (sonnet).
  - Wave 2: data management plans plus Borealis/FRDR (sonnet), in-app bring-your-own-key assistant (sonnet).
  - Then a security review, fixes, screenshots and a push.
- **Postgres rule:** one test container per agent, scoped tests only. The orchestrator runs the full suite.

