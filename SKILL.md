---
name: autocatalyst
description: subagent-native incumbent-challenger workflow for ideation, concept descriptions, proposals, wireframes, specs, implementation plans, and code or feature improvements. use when you want codex to explicitly spawn real subagents for planning, research, critique, challenger generation, synthesis, or blind judging instead of simulating fresh perspectives in one shared context. also use when you want repo artifacts, resumable round logs, mermaidjs flowcharts, a browser-viewable html report, web browsing by default, cross-platform bootstrap helpers, and recurring critiques promoted into rubrics, tests, or checks. do not use for trivial one-step edits or pure factual lookup requests.
---

# AutoCatalyst

Run AutoCatalyst as a **subagent-native** incumbent–challenger workflow.

Treat every task as an **anchor + incumbent + challengers + tribunal + convergence** system:

- **Anchor**: the stable objective, audience, constraints, deliverables, and non-goals.
- **Incumbent `A`**: the current best artifact, draft, spec, plan, or implementation.
- **Catalyst critique**: a fresh problem-only attack on `A`.
- **Challengers**:
  - `A` = keep the incumbent unchanged
  - `B` = revise `A` to address the strongest valid critique
  - `AB` = synthesize the strongest parts of `A` and `B`
- **Tribunal**: hard checks, benchmarks, blind judges, or a hybrid mix.
- **Convergence**: stop when the incumbent survives repeated fresh challenge or when new critiques no longer produce credible gains.

## Mandatory operating rule

**Do not simulate planner, researcher, critic, rewriter, synthesizer, or judges in the main thread when full AutoCatalyst mode is requested.**

Codex only spawns subagents when explicitly asked, so full AutoCatalyst mode must explicitly delegate real work to custom agents and wait for their results. If the environment does not actually spawn subagents, report **`degraded single-agent mode`** and stop unless the user explicitly accepts the fallback. Do not pretend a blind panel happened when it did not.

## Work from the repository root

Use repository-root paths whenever possible.

Run setup commands from the **target repository root**, not from the global skill directory. Keep `--root .` pointed at the repo you want to initialize.

Keep durable state in these files:

- `autocatalyst.md`
- `autocatalyst.jsonl`
- `autocatalyst-rubric.md`
- `autocatalyst-dashboard.md`
- `autocatalyst-artifacts/`
- optional `autocatalyst.checks.py` or another supported checks hook such as `.ps1`, `.cmd`, or `.sh`

Prefer helper scripts for initialization, subagent installation, logging, and Mermaid/dashboard rendering.
Prefer the convergence helper to decide whether another round should run:

```bash
python3 .agents/skills/autocatalyst/scripts/check_convergence.py --root .
```

## First-run setup

Bootstrap from the **target repository root** before the first full round.

If `autocatalyst.md` is missing, if `.codex/agents/autocatalyst_critic.toml` is missing, or if the repo was moved to a new absolute path, **bootstrap automatically before doing any real work**. Do not wait for the user to remember setup commands.

Important:

- Never paste literal angle-bracket placeholders such as `<goal>` into shell commands. Use a real quoted string instead.
- Choose the wrapper that matches the current environment. The wrappers select a working Python launcher automatically.
- Keep `--root .` pointed at the target repo.
- Minimum supported Python version is `3.10`; `3.11+` is recommended.
- If the runtime is Python `3.10`, install `tomli` so the TOML-reading helpers can parse `.toml` files.
- The generated `.codex/agents/*.toml` files describe the intended role and sandbox posture, but the active Codex session still controls what child agents can actually do at runtime.
- If the parent session blocks network, approvals, or child depth, AutoCatalyst inherits that limitation.

### Repo-local skill install

If the skill lives inside the target repo at `.agents/skills/autocatalyst/`, prefer these commands from the repo root:

**Windows PowerShell**

```powershell
.\.agents\skills\autocatalyst\scripts\autocatalyst.ps1 --root . --goal "Improve the current repository deliverable" --install-agents-md
```

**Windows cmd.exe**

```cmd
.\.agents\skills\autocatalyst\scripts\autocatalyst.cmd --root . --goal "Improve the current repository deliverable" --install-agents-md
```

**macOS / Linux / WSL**

```bash
sh ./.agents/skills/autocatalyst/scripts/autocatalyst.sh --root . --goal "Improve the current repository deliverable" --install-agents-md
```

### Global skill install

If the skill is installed globally instead of inside the repo, call the matching wrapper or `bootstrap.py` by **absolute path**, but still run from the repo root and keep `--root .` pointed at the repo.

Examples:

```powershell
py -3 C:\path\to\autocatalyst\scripts\bootstrap.py --root . --goal "Improve the current repository deliverable" --task-class hybrid --evidence-mode hybrid --install-agents-md
```

```bash
python3 /path/to/autocatalyst/scripts/bootstrap.py --root . --goal "Improve the current repository deliverable" --task-class hybrid --evidence-mode hybrid --install-agents-md
```

### Idempotent bootstrap behavior

The bootstrap is safe to rerun. It should:

- install missing subagents
- initialize missing session files
- refresh `autocatalyst-dashboard.md`
- refresh Mermaid artifacts
- refresh `autocatalyst-report.html`

If the repo already has a session, bootstrap should refresh the derived files instead of clobbering the state.

### Direct Python helpers

Use these when the wrapper scripts are not convenient:

```bash
python3 .agents/skills/autocatalyst/scripts/init_session.py --root . --goal "Improve the current repository deliverable" --task-class hybrid --evidence-mode hybrid --install-subagents --install-agents-md
python3 .agents/skills/autocatalyst/scripts/install_subagents.py --root .
python3 .agents/skills/autocatalyst/scripts/render_dashboard.py --root .
python3 .agents/skills/autocatalyst/scripts/check_convergence.py --root .
python3 .agents/skills/autocatalyst/scripts/resolve_subagent_profiles.py --root .
```

On Windows, prefer `py -3` over `python3` when `python3` is not available.

## Task classes

Classify the task before the first round:

1. **Ideation**
   - concept descriptions
   - proposals
   - brainstorming
   - naming systems
   - wireframes

2. **Planning / specification**
   - specs
   - PRDs
   - architecture notes
   - implementation plans
   - prompt specs

3. **Implementation**
   - code changes
   - tests
   - refactors
   - feature delivery
   - docs tied to code

4. **Hybrid**
   - concept + spec
   - plan + implementation
   - research + proposal + code

## Evidence-mode election

Choose one evidence mode before challenger generation:

- **`judge-first`** when the artifact is mainly about usefulness, clarity, strategy, originality, taste, or persuasion.
- **`benchmark-first`** when success is mostly captured by tests, latency, pass rate, cost, size, or another trusted metric.
- **`hybrid`** when hard checks matter but human judgment still decides quality.

When evidence mode is ambiguous, spawn `autocatalyst_selector` and use it to choose between `judge-first`, `benchmark-first`, and `hybrid`.

## Browse by default

Browse the web by default whenever external facts, APIs, frameworks, libraries, competitors, standards, or current product capabilities matter.

- Prefer official or primary sources.
- Use repo files, provided links, screenshots, and web sources together.
- Cite factual claims in the final artifact when external sources influenced the result.
- Distinguish sourced facts from inference.

## Install and use real custom agents

Use the custom agents installed at `.codex/agents/`:

- `autocatalyst_selector`
- `autocatalyst_planner`
- `autocatalyst_researcher`
- `autocatalyst_critic`
- `autocatalyst_rewriter`
- `autocatalyst_synthesizer`
- `autocatalyst_judge`

Important:

- The generated `.codex/agents/*.toml` files define the role and sandbox posture. They do **not** pin the model.
- Model choice happens when the parent agent spawns each subagent.
- Resolve model settings before spawning:

```bash
python3 .agents/skills/autocatalyst/scripts/resolve_subagent_profiles.py --root .
```

- Precedence is:
  1. role override from `.codex/autocatalyst-models.toml`
  2. `[defaults]` from `.codex/autocatalyst-models.toml`
  3. fallback from `.codex/config.toml`
  4. otherwise inherit the parent/default model
- Pass the resolved `model` and `reasoning_effort` values into each `spawn_agent(...)` call.

Use [references/subagents.md](references/subagents.md) for the exact role packets and example delegation language.

## Respect runtime limits when spawning

This skill runs under the repository's active Codex agent limits.

In this repository, `.codex/config.toml` currently sets:

- `max_threads = 6`
- `max_depth = 3`

Treat those values as a hard operational budget.

Rules:

- close stale, completed, or abandoned child agents before starting the next stage
- do not leave critique, challenger, and judge threads open longer than needed
- keep child depth flat; do not ask child agents to spawn their own agent trees
- when headroom is unclear, prefer bounded batches over one large fan-out

Practical consequence for blind judging:

- a tribunal still needs three real judges
- but it does **not** require spawning all three at the exact same moment
- it is valid to run them as bounded batches such as `1 + 2` or `2 + 1`
- aggregate only after all three real judgments are collected

If the environment cannot supply enough headroom for the next required batch, stop and report the limitation instead of pretending the panel happened.

## Keep context packets narrow

Pass only the minimum context each role needs.

- **selector**: anchor, repo scope, evaluation stakes, explicit deliverables
- **planner**: anchor, repo scope, current inputs, explicit deliverables
- **researcher**: precise research questions, links, repo paths, required citation style
- **critic**: anchor + incumbent `A` only
- **rewriter**: anchor + `A` + critique + evidence packet if relevant
- **synthesizer**: anchor + `A` + `B` + critique summary if needed
- **judge panel**: anchor + rubric + per-judge blinded candidate aliases only

Do not leak prior verdicts, author labels, or raw research sprawl into judge context.

## Orchestration protocol

Run the round in this order.

### 1. Anchor the task

Restate:

- exact objective
- audience
- required deliverables
- hard constraints
- non-goals
- files in scope
- evidence mode

Write or refresh `autocatalyst.md` and `autocatalyst-rubric.md` when the task is resumable or likely to take more than one round.

### 2. Establish the incumbent `A`

- Prefer an existing repo artifact when one already exists.
- If no artifact exists, create a fast first version and explicitly label it `A`.
- Preserve `A` as a control arm; do not silently overwrite it before the tribunal.

### 3. Optional research pass

If the task depends on external facts, spawn `autocatalyst_researcher` with bounded questions and wait for the evidence packet before critique or rewriter work.

### 4. Catalytic critique

Spawn `autocatalyst_critic` on **anchor + `A` only**.

Require a **problems-only** critique:

- list the highest-impact weaknesses first
- separate hard blockers from softer concerns
- identify what could become an explicit rubric item, acceptance criterion, or test
- **do not propose fixes**

### 5. Generate challenger `B`

Spawn `autocatalyst_rewriter` on **anchor + `A` + critique (+ evidence packet when relevant)**.

For write-heavy tasks, isolate the candidate:

- prefer candidate-specific files under `autocatalyst-artifacts/rounds/<round>/`
- or use worktrees / isolated paths if the repo workflow supports them
- do not let multiple write agents race on the same canonical file

### 6. Generate synthesis `AB`

Spawn `autocatalyst_synthesizer` on **anchor + `A` + `B`**.

Require synthesis rather than averaging:

- keep only the strongest parts of `A`
- absorb only the strongest valid improvements from `B`
- avoid bloated “include everything” mergers

### 7. Apply hard checks

Run the strongest relevant hard checks before blind judgment. Prefer the cross-platform helper when a repo-local checks hook exists.

Examples:

- tests
- lint / formatting
- type checks
- build success
- benchmarks
- citation sanity checks
- compatibility checks
- `python3 .agents/skills/autocatalyst/scripts/run_checks.py --root .` when a repo-local checks hook exists

For implementation tasks, treat passing tests as necessary but not always sufficient.

### 8. Run the tribunal

For blind judging, collect **three** real `autocatalyst_judge` results from per-judge blinded packets and aggregate the ranking conservatively. Under tight thread limits, run the panel in bounded batches instead of forcing all three judges to exist simultaneously.

Tribunal order:

1. eliminate candidates that fail hard checks
2. use benchmark evidence when it is trustworthy
3. use the blind panel for the remaining ambiguity
4. keep `A` when evidence is mixed and the challenger does not clearly improve the result

Use ranked choice or Borda-style aggregation when useful.

### 9. Promote the winner

- if `A` wins, increment the survival streak
- if `B` or `AB` wins, reset the survival streak and make the winner the new incumbent
- update the canonical repo artifact only after the tribunal
- record what won and why
- write a human-readable round casefile for the winning round

Recommended artifact:

- `autocatalyst-artifacts/rounds/round-<n>-casefile.md`

That file should be the cold-reader narrative of the round:

- what the user wanted
- what was wrong with the starting point
- what contenders were explored
- what the judges decided and why
- what changed afterward

### 9.5. Check convergence before starting another round

Compute convergence from the logged session state:

```bash
python3 .agents/skills/autocatalyst/scripts/check_convergence.py --root .
```

Treat the helper output as authoritative for the incumbent survival rule:

- if it says `decision = "stop"`, stop the AutoCatalyst loop
- if it says `decision = "continue"`, another round is still allowed

Other convergence rules still apply even when the helper says `continue`:

- benchmark gains flatten
- judges keep repeating minor feedback
- the user redirects the task
- the artifact is already good enough for handoff

### 10. Promote recurring critiques into durable guards

When the same criticism appears at least twice, convert it into something explicit.

For code work, prefer:

- tests
- benchmarks
- assertions
- lint rules
- type checks
- regression checks

For concepts, specs, prompts, and plans, prefer:

- rubric items
- acceptance criteria
- non-goals
- glossary terms
- comparison axes
- examples
- risk sections

## Mermaid artifacts are mandatory

Leave behind MermaidJS visualizations of the process.

At minimum, keep these files current:

- `autocatalyst-artifacts/process-overview.md`
- `autocatalyst-artifacts/session-history.md`
- `autocatalyst-artifacts/rounds/round-<n>-flow.md` for each logged round

Use the helper scripts instead of hand-drawing when possible. Rendering refreshes the markdown dashboard, Mermaid artifacts, and the browser-viewable `autocatalyst-report.html` file:

```bash
python3 .agents/skills/autocatalyst/scripts/render_dashboard.py --root .
```

If you log rounds with the helper, it will also refresh the Mermaid artifacts and browser report:

```bash
python3 .agents/skills/autocatalyst/scripts/log_round.py --root . --round 1 --winner AB --status promote --winner-reason "AB merged the strongest ideas and clarified the next steps" --hard-checks pass
```

When a round casefile exists, include it in the logged artifact paths. The HTML report should treat that casefile as the primary narrative and use JSONL and the other artifacts as supporting evidence.

Use [references/artifact-templates.md](references/artifact-templates.md) for Mermaid-ready templates.

## Degraded-mode guardrails

If custom agents are missing, install them before continuing.

If Codex still does not actually spawn subagents:

1. stop the full AutoCatalyst run
2. state `degraded single-agent mode`
3. explain which required agents were not spawned
4. ask the user to accept fallback explicitly before simulating the process in one thread

Do not claim:

- a blind panel existed,
- a fresh critique existed,
- or a real evidence-mode vote happened,

unless those subagents actually ran.

## Resume discipline

When resuming:

1. read `autocatalyst.md`
2. read `autocatalyst.jsonl`
3. read `autocatalyst-rubric.md`
4. read `autocatalyst-dashboard.md`
5. read current artifacts under `autocatalyst-artifacts/`
6. continue from the current incumbent instead of restarting blindly
7. refresh the browser report if the dashboard or Mermaid files are stale

## Logging discipline

After each round, append a structured round row and refresh the dashboard, Mermaid files, and browser report.

Prefer the helper script with real values, not literal angle-bracket placeholders:

```bash
python3 .agents/skills/autocatalyst/scripts/log_round.py --root . --round 1 --winner AB --status promote --winner-reason "AB merged the strongest ideas and passed the current checks" --hard-checks pass
```

When a round used blinded judging, also log the tribunal structure explicitly:

- `--critic-output-artifact <path>` when you saved a structured critic output
- `--researcher-output-artifact <path>` when you saved a structured researcher output
- `--candidate-map-artifact <path>`
- `--tribunal-summary-artifact <path>`
- `--judge-verdict-artifact judge1=<path>` repeated per judge
- `--judge-panel-ranking "judge1=Candidate 2>Candidate 1>Candidate 3"` repeated per judge
- `--aggregation-method "<description>"`

Judge, critic, and researcher outputs can end with a structured JSON block. Validate those saved artifacts with:

```bash
python3 .agents/skills/autocatalyst/scripts/validate_structured_output.py --role judge --file /path/to/output.md
```

When you later call `log_round.py`, prefer passing the saved verdict / critic / researcher / tribunal artifacts in the `--artifact` list. The logger can auto-discover and ingest those structured outputs instead of forcing the parent to repeat every path in dedicated flags.

Use [references/workflow.md](references/workflow.md) for round structure, [references/evidence-modes.md](references/evidence-modes.md) for evidence-mode selection, [references/subagents.md](references/subagents.md) for role packets, and [references/artifact-templates.md](references/artifact-templates.md) for output templates.
