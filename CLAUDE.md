# CLAUDE.md

Product and history live in `docs/` (VISION.md for direction, SPEC.md for what we build,
DECISIONS.md for why). Read the relevant part before changing behaviour.

## Delegating work: match the model to the job

The founders' rule: do not throw resources at work that does not need them. Follow this on every
task, for subagents, workflows and swarms.

**First, decide whether to delegate at all.** Do it yourself, inline, when the job is a handful of
tool calls, a lookup you already know where to make, back-and-forth with the user, or one step of a
chain where each step needs the last one's context. A subagent buys parallelism or a fresh pair of
eyes, not a smarter answer, and it pays to re-read context. Delegate only independent pieces, or
work too big for one context.

**Then pick the cheapest model that will do it well:**

| Model | Use it for | Examples here |
|---|---|---|
| Haiku | Simple, self-contained, well-specified jobs | Help-page or doc text from a precise brief, renames, link checks, finding every caller of a function, running the tests and reporting failures |
| Sonnet | Routine feature work with a clear spec | A DRF endpoint or React component to spec, polling and UI states, tests for existing code, applying review findings |
| Opus | Work where a mistake is costly or the design is open | Permissions, tenancy, auth, anything touching participant data or AI access, token and upload handling, multi-file features, migrations, security review, orchestrating a swarm |
| Fable | Rarely: costs about twice Opus | Root-cause hunts and architecture decisions too big for one sitting. Ask the user first |

**Effort:** start at medium. Use low for mechanical stages, high for security work and for fixes
where edge cases matter, and max only for unsupervised security hunting (it overthinks normal work).
Before adding a second model, try changing the first one's effort.

**Swarms:** an Opus orchestrator with Sonnet workers is the default shape. Use Haiku workers only for
genuinely simple pieces, because they lose accuracy on real coding. Every security-sensitive change
gets a separate read-only reviewer (Opus) that did not write it, and a cheaper fixer applies what
the review confirms. Keep it to about 2 to 5 workers per feature unless the user asks for more.
Each worker gets a written brief: goal, files, what is already ruled out, and how to report.

## Parallel agents on this machine (Windows)

- Workflow `isolation: 'worktree'` fails here. Make worktrees by hand under `.night/<slug>` (already in
  `.git/info/exclude`), one branch each, and give agents `.night/RULES.md`.
- Never use `git stash`: stashes are shared across worktrees.
- Run frontend tests in docker (`make test-frontend`, or `docker run ... research-platform-frontend`).
  Host vitest is broken on this machine.
- The backend `pytest -q` summary line is often swallowed: check the exit code.
- The cofounder pushes to `main` directly. `git fetch` and check
  `git merge-base --is-ancestor origin/main HEAD` before every push. Every push to `main` deploys to
  the live site, and nothing else runs the tests, so run the full gate first.

## Hard rules

- Lab data is lab-scoped; permission checks go through `backend/core/permissions.py`; sensitive
  actions write audit events. Never weaken a permission check to pass a test.
- Participant data: items flagged "Contains participant data" never reach any AI tool.
- Secrets come from the environment. Never open or print `.env`, `.env.qa` or `deploy/.env.prod`.
- Seed and test data must be obviously fake (example.test).
- New dependencies must be MIT, BSD, Apache, ISC or MPL-2.0. Never install `@blocknote/xl-*` and never
  read or copy GPL or AGPL code.
