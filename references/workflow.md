# Workflow Reference

## Contents
- [Round shape](#round-shape)
- [Tribunal order](#tribunal-order)
- [Logging schema](#logging-schema)
- [Convergence](#convergence)
- [Research-heavy tasks](#research-heavy-tasks)
- [Implementation-heavy tasks](#implementation-heavy-tasks)

## Round shape

Run every AutoCatalyst round in this order.

### 1. Setup

- read the current repo state, screenshots, links, and existing drafts
- initialize or refresh `autocatalyst.md`
- initialize or refresh `autocatalyst-rubric.md`
- confirm the canonical output path for the current incumbent
- confirm the candidate output paths for round `n`

### 2. Evidence-mode choice

- choose `judge-first`, `benchmark-first`, or `hybrid`
- when uncertain, use the real planner/critic/judge vote
- write the chosen mode and rationale into `autocatalyst.md`

### 3. Incumbent `A`

- prefer an existing artifact when one already exists
- otherwise create a quick but explicit first version and label it `A`
- preserve `A` as the control arm

### 4. Research pass when needed

- use the researcher for external grounding
- keep the evidence packet concise
- feed only decision-relevant findings into later packets

### 5. Catalytic critique

- run the critic on anchor + `A`
- demand problems only
- separate severe issues from softer concerns
- identify which complaints could become durable checks or rubric items

### 6. Generate `B`

- run the rewriter on anchor + `A` + critique (+ evidence packet if relevant)
- write `B` to a candidate-specific path
- preserve valid strengths of `A`
- fix the strongest valid weaknesses first

### 7. Generate `AB`

- run the synthesizer on anchor + `A` + `B`
- write `AB` to a candidate-specific path
- keep only the best parts of both candidates
- avoid bloated “kitchen sink” syntheses

### 8. Hard checks

Run all relevant hard gates before judging:

- tests
- lint / formatting
- type checks
- build
- benchmark
- citation sanity checks
- compatibility checks
- `python3 .agents/skills/autocatalyst/scripts/run_checks.py --root .` when a repo-local checks hook exists

### 9. Blind tribunal

- anonymize `A`, `B`, `AB`
- spawn three judges
- wait for all three results
- aggregate the rankings conservatively
- keep `A` when the evidence is close

### 10. Promotion

- if `A` wins, keep the incumbent and increment the survival streak
- if `B` or `AB` wins, promote the winner and reset the streak
- update the canonical artifact only after the tribunal

### 11. Logging and rendering

- append one structured `round` row to `autocatalyst.jsonl`
- regenerate `autocatalyst-dashboard.md`
- regenerate Mermaid flow artifacts
- regenerate `autocatalyst-report.html`

Prefer the helper with real values. Logging also refreshes the browser report:

```bash
python3 .agents/skills/autocatalyst/scripts/log_round.py --root . --round 1 --winner AB --status promote --winner-reason "AB merged the strongest ideas and clarified the next steps" --hard-checks pass
```

## Tribunal order

Use the strongest available evidence in this order:

1. eliminate candidates that fail hard checks
2. compare reliable benchmark evidence when present
3. use blind judges for the remaining ambiguity
4. favor the incumbent when evidence is mixed or weak

Good default interpretations:

- `judge-first` → judges dominate, hard checks only guard obvious failures
- `benchmark-first` → metrics dominate, judges break ties or inspect quality regressions
- `hybrid` → metrics narrow the field, judges decide the remaining ambiguity

## Logging schema

Use one `config` row at session start and one `round` row per round.

### Config row example

```json
{"type":"config","name":"example goal","taskClass":"ideation","evidenceMode":"hybrid","survivalTarget":2}
```

### Round row fields

Use these fields consistently when possible:

- `type`: `round`
- `round`: integer round number
- `evidenceMode`: `judge-first|benchmark-first|hybrid`
- `winner`: `A|B|AB`
- `status`: `promote|keep|mixed|blocked|rejected`
- `winnerReason`: short explanation
- `hardChecks`: `pass|fail|mixed|na`
- `judgeRanking`: ordered list such as `A,AB,B`
- `incumbentBefore`: path or label
- `incumbentAfter`: path or label
- `artifacts`: output files written this round
- `promotions`: promoted rubric items, checks, or acceptance criteria
- `degradedMode`: `true|false`
- `agentNames`: names of the agents that actually ran

The helper script handles the JSON structure for you.

## Convergence

Stop when one of these becomes true:

- the incumbent survives at least two fresh challenge rounds
- benchmark gains flatten and the added complexity is no longer justified
- judges keep repeating the same minor feedback without changing the winner
- the user interrupts or redirects the task
- the artifact is good enough for handoff

## Research-heavy tasks

When the task depends on current information:

- browse by default
- prefer official docs, standards, papers, and primary sources
- keep raw research out of judge context unless it is part of the artifact
- preserve only the decision-relevant evidence in the session files

## Implementation-heavy tasks

When code changes are in play:

- keep candidate edits isolated
- avoid parallel edits to the same canonical file
- run cheap hard checks early, preferably through `.agents/skills/autocatalyst/scripts/run_checks.py` when the repo defines an AutoCatalyst checks hook
- treat passing tests as necessary but not always sufficient
- use judges for readability, maintainability, or design quality when those matter
