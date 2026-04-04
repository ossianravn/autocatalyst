# Subagent Reference

## Contents
- [Install the project-scoped agents](#install-the-project-scoped-agents)
- [Required agents](#required-agents)
- [Role packets](#role-packets)
- [Delegation language](#delegation-language)
- [Blind judging rules](#blind-judging-rules)
- [Write-heavy task safety](#write-heavy-task-safety)
- [Degraded mode](#degraded-mode)

## Install the project-scoped agents

Install the custom agents into the repository before the first full AutoCatalyst run. Prefer the idempotent bootstrap from the target repository root so missing session files and missing agent files are handled together.

Never paste literal placeholders such as `<goal>` into shell commands. Use a real quoted goal string.

### Repo-local skill install

If the skill has been installed into the repo at `.agents/skills/autocatalyst/`, prefer:

```powershell
.\.agents\skills\autocatalyst\scripts\autocatalyst.ps1 --root . --goal "Improve the current repository deliverable" --install-agents-md
```

```bash
sh ./.agents/skills/autocatalyst/scripts/autocatalyst.sh --root . --goal "Improve the current repository deliverable" --install-agents-md
```

### Global skill install

If the skill is only available from a global Codex skill directory, call the matching wrapper or `bootstrap.py` by absolute path but keep `--root .` pointed at the repo.

```bash
python3 /path/to/autocatalyst/scripts/bootstrap.py --root . --goal "Improve the current repository deliverable" --task-class hybrid --evidence-mode hybrid --install-agents-md
```

This creates `.codex/agents/` files for project-scoped agents and refreshes the dashboard, Mermaid artifacts, and browser report.

If the repository moves to a new absolute path, rerun the bootstrap or install script so the agent files can refresh the path they use to disable the AutoCatalyst skill inside child sessions.

## Required agents

Use these agents:

- `autocatalyst_selector`
- `autocatalyst_planner`
- `autocatalyst_researcher`
- `autocatalyst_critic`
- `autocatalyst_rewriter`
- `autocatalyst_synthesizer`
- `autocatalyst_judge`

Use exactly these responsibilities:

- **selector**: choose the evidence mode and tribunal posture
- **planner**: classify task class, recommend evidence mode, draft the round plan
- **researcher**: gather evidence and citations, not solutions
- **critic**: attack the incumbent, problems only
- **rewriter**: produce candidate `B`
- **synthesizer**: produce candidate `AB`
- **judge**: blind evaluation only

Do not merge roles in one child agent.

## Runtime model selection

Use the generated `.codex/agents/*.toml` files for role behavior only.

- Do not assume those files pin the model.
- Choose `model` and `reasoning_effort` when the parent spawns each agent.
- Resolve settings first:

```bash
python3 .agents/skills/autocatalyst/scripts/resolve_subagent_profiles.py --root .
```

- Precedence is:
  1. role override from `.codex/autocatalyst-models.toml`
  2. `[defaults]` from `.codex/autocatalyst-models.toml`
  3. fallback from `.codex/config.toml`
  4. otherwise inherit the parent/default model
- Pass the resolved values into `spawn_agent(...)` for each role.

Typical profile split:

- selector, planner, researcher: `gpt-5.4`
- critic: `gpt-5.4` with lighter reasoning when appropriate
- rewriter, synthesizer, judge: see `.codex/autocatalyst-models.toml` or the example file

## Runtime limits and batching

Always check the repo's active `.codex/config.toml` before assuming a fan-out pattern is safe.

In this repository the active policy is:

- `max_threads = 6`
- `max_depth = 3`

Operational rules:

- close stale, completed, or abandoned child agents before spawning the next stage
- keep only the current stage's agents alive
- do not ask child agents to spawn more agents
- when headroom is uncertain, prefer bounded batches over one broad burst

Blind judging still requires three real judges, but those results may be gathered in bounded batches such as `1 + 2` or `2 + 1` and then aggregated after all three verdicts exist.

## Role packets

Keep every packet narrow.

### Planner packet

Include:

- task statement
- audience
- deliverables
- files in scope
- hard constraints
- repo paths or screenshots that matter

Request:

- task class
- evidence-mode recommendation
- candidate-isolation plan
- suggested artifact paths
- initial rubric headings

### Selector packet

Include:

- task statement
- audience
- deliverables
- hard constraints
- repo paths or screenshots that matter

Request:

- evidence-mode choice
- short rationale
- main decision signal
- missing inputs if the task is underspecified

### Researcher packet

Include:

- concrete research questions
- provided links
- official docs or standards to check
- any repo paths that frame the question

Request:

- concise evidence packet
- source-backed facts
- unresolved questions
- implications for the artifact

Do not ask for a finished concept, plan, or implementation.

### Critic packet

Include only:

- anchor
- incumbent `A`

Request:

- most severe issues first
- hard blockers vs softer concerns
- no fixes
- no replacement draft
- note which issues could become explicit checks

### Rewriter packet

Include:

- anchor
- incumbent `A`
- critique
- evidence packet when relevant
- exact output path for candidate `B`

Request:

- write or revise candidate `B`
- preserve the valid strengths of `A`
- address the strongest valid critiques first
- summarize changed paths, rationale, and residual risks

### Synthesizer packet

Include:

- anchor
- `A`
- `B`
- short critique summary when helpful
- exact output path for candidate `AB`

Request:

- merge only the strongest pieces of `A` and `B`
- avoid “include everything” behavior
- summarize what was preserved, added, and intentionally dropped

### Judge packet

Include only:

- anchor
- rubric
- per-judge blinded candidate aliases only

Request:

- independent ranking best-to-worst
- winner
- short rationale
- blocker callout if something disqualifies a candidate
- final structured JSON block using schema `autocatalyst.judge.v1`

Do not reveal or mention any author labels, earlier verdicts, or internal process history.

## Delegation language

Use direct language that explicitly tells Codex to spawn agents and wait.

### Evidence-mode vote example

```text
Spawn three subagents and wait for all of them:
1. autocatalyst_selector
Give it the anchor packet only.
Ask it to choose judge-first, benchmark-first, or hybrid and explain why.
Return the evidence-mode choice and any missing inputs it flags.
```

### Critique example

```text
Spawn autocatalyst_critic and wait for the result.
Give it the anchor and incumbent A only.
If a resolved profile exists for the critic, pass its model and reasoning settings explicitly.
Require a problems-only critique: severe issues first, no fixes, no rewrite.
Require the final response to end with the structured JSON block described by the critic schema.
```

### Challenger example

```text
Spawn autocatalyst_rewriter and wait for the result.
Give it the anchor, incumbent A, the critique, any evidence packet, and the exact output path for candidate B.
If a resolved profile exists for the rewriter, pass its model and reasoning settings explicitly.
```

### Synthesis example

```text
Spawn autocatalyst_synthesizer and wait for the result.
Give it the anchor, candidate A, candidate B, and the output path for candidate AB.
If a resolved profile exists for the synthesizer, pass its model and reasoning settings explicitly.
```

### Blind panel example

```text
Collect three real autocatalyst_judge verdicts.
Give each judge the anchor, rubric, and a per-judge blinded candidate packet only.
If a resolved judge profile exists, pass its model and reasoning settings to each judge spawn.
Under thread pressure, run the judges in bounded batches and close completed judges before starting the next batch.
Return each ranking and a consolidated winner.
```

## Structured output blocks

For roles whose outputs are later aggregated, prefer a dual-format response:

1. a short human-readable result
2. a final `## Structured Output` section containing one fenced `json` block

Current recommended schemas:

- judge: `autocatalyst.judge.v1`
- critic: `autocatalyst.critic.v1`
- researcher: `autocatalyst.researcher.v1`

If you save one of those outputs to disk, validate it with:

```bash
python3 .agents/skills/autocatalyst/scripts/validate_structured_output.py --role judge --file /path/to/output.md
```

Swap `judge` for `critic` or `researcher` as needed.

## Blind judging rules

Enforce all of these:

- anonymize candidate labels consistently
- permute candidate order separately for each judge when possible
- do not tell the judges which candidate is the incumbent
- do not show judges one another’s verdicts before they decide
- do not show judges the critique, research notes, or implementation history unless that is part of the artifact being judged
- prefer conservative promotion when rankings are close

## Write-heavy task safety

Use parallel agents aggressively for read-heavy work.

Be more careful for write-heavy work:

- avoid concurrent edits to the same canonical file
- prefer candidate-specific files under `autocatalyst-artifacts/rounds/<n>/`
- use worktrees or isolated temp files when the repo workflow supports them
- apply hard checks before copying a winning challenger into the canonical path

Typical safe order:

1. researcher (optional)
2. critic
3. rewriter
4. synthesizer
5. hard checks
6. three judges
7. promotion

## Degraded mode

Treat full AutoCatalyst mode as unavailable when:

- the required custom agents are not installed,
- Codex does not actually spawn subagents,
- child threads cannot run because the environment blocks them,
- or the session approval/sandbox posture prevents the needed actions and the user has not accepted the limitation.

In degraded mode:

- say `degraded single-agent mode`,
- identify the missing delegation step,
- avoid claiming a real panel or fresh critique existed,
- wait for explicit user approval before simulating the workflow in one thread.

## Runtime inheritance caveat

The generated `.codex/agents/*.toml` files define the intended role and sandbox posture for each child agent. They do not override the active Codex session.

Operationally that means:

- the parent session still controls whether child agents can actually spawn
- the parent session still controls approval posture
- the parent session still controls network posture
- the parent session still controls effective child-depth limits

If the parent/runtime blocks one of those capabilities, treat that as an environment limitation rather than assuming the `.toml` file will force a different outcome.
