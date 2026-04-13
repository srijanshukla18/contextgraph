# Human TODO for Launch: ContextGraph

**The codebase is complete and hardened for production. The API, UI Explorer, and SDKs (LangGraph, OpenAI, Claude) are ready to go.**

Your goal for ContextGraph is to launch it as the "Picks and Shovels of the AI Gold Rush" — specifically targeting developers and enterprises who are terrified of black-box AI agents and need a structured, queryable decision ledger for compliance and observability.

## 1. Infrastructure & Backend Deployment
- [ ] Spin up a managed PostgreSQL database (e.g., Supabase, RDS, or Railway).
- [ ] Execute `storage/postgres/schema.sql` against your new production database to create the required tables and indexes.
- [ ] Deploy the `server` using the provided `Dockerfile` to your hosting provider (Render, Railway, or Heroku).
- [ ] Set your production environment variables on the host:
  - `DATABASE_URL`
  - `API_KEYS` (Generate a secure, comma-separated list of keys for your early users/yourself)
  - `ALLOWED_ORIGINS` (Include the URL where you'll host the UI Explorer)
  - `REQUIRE_AUTH=true`

## 2. UI Explorer Deployment
- [ ] The `ui/index.html` file is a standalone SPA. Host it on Vercel, Netlify, or GitHub Pages.
- [ ] Ensure the UI is configured to hit your production API URL (you can set the default in the HTML or let users input it).

## 3. The "Show, Don't Tell" Launch Assets
- [ ] **Record a 60-second Loom Demo:**
  - Start by showing an AI agent executing a complex, risky task (like issuing a $8,000 refund or service credit).
  - Open the **ContextGraph UI Explorer** and show the visual "why chain": Evidence → Policy → Human Approval → Action.
  - Run a quick `curl` or show a script querying the `/v1/precedents/search` endpoint to prove that decisions are now queryable data.
- [ ] **Take 3-4 Screenshots:**
  - The UI Explorer showing a fully expanded decision trace with the "pass/fail" badges on policies.
  - A side-by-side snippet: 3 lines of LangGraph code initializing the `ContextGraphCheckpointer`, next to the resulting JSON `DecisionRecord`.

## 4. Community Launch (The Strategy)
- [ ] Package the `sdk/python` directory and publish it to PyPI (`pip install contextgraph`).
- [ ] Publish an article on Medium / Hacker News titled: *"Why your AI Agents will fail compliance audits (and how to fix it)."*
- [ ] Launch on r/MachineLearning, r/LangChain, and Hacker News (`Show HN:`).
- [ ] **The Hook:** *"I got tired of not knowing why my AI agents were failing or making risky choices, so I built a self-serve visual debugger and decision ledger for LLMs."*
