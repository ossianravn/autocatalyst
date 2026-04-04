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

- prepare per-judge blinded candidate aliases
- collect three real judges
- under thread limits, gather those verdicts in bounded batches rather than forcing all three judges to be alive at once
- close completed or abandoned judges before starting the next batch
- aggregate the rankings conservatively
- keep `A` when the evidence is close

Prefer using the helper when you want a repeatable setup:

```bash
python3 .agents/skills/autocatalyst/scripts/prepare_judge_packets.py --root . --round 1 --anchor autocatalyst.md --rubric autocatalyst-rubric.md --candidate A=path/to/a.md --candidate B=path/to/b.md --candidate AB=path/to/ab.md
```

That helper creates:

- per-judge blinded packet files
- a parent-only candidate map
- a tribunal summary markdown stub
- a parseable tribunal summary JSON companion

### 10. Promotion

- if `A` wins, keep the incumbent and increment the survival streak
- if `B` or `AB` wins, promote the winner and reset the streak
- update the canonical artifact only after the tribunal
- write a human-readable round casefile artifact before or alongside promotion

Recommended file:

- `autocatalyst-artifacts/rounds/round-<n>-casefile.md`

That casefile should explain the round for a cold reader:

- what the user wanted
- what was wrong with the starting point
- what contenders were compared
- what the judges decided and why
- what changed afterward

### 11. Logging and rendering

- append one structured `round` row to `autocatalyst.jsonl`
- include the round casefile artifact path in the logged artifacts when one exists
- include tribunal artifacts such as judge packets, candidate maps, verdicts, and tribunal summaries when they exist
- regenerate `autocatalyst-dashboard.md`
- regenerate Mermaid flow artifacts
- regenerate `autocatalyst-report.html`
- compute convergence before starting the next round

Prefer the helper with real values. Logging also refreshes the browser report:

```bash
python3 .agents/skills/autocatalyst/scripts/log_round.py --root . --round 1 --winner AB --status promote --winner-reason "AB merged the strongest ideas and clarified the next steps" --hard-checks pass
```

Then check whether another round should run:

```bash
python3 .agents/skills/autocatalyst/scripts/check_convergence.py --root .
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
- `critic.artifact`: saved critic output artifact when a structured critic output was logged
- `critic.rewriteWarranted`: boolean
- `critic.hardBlockers`: structured hard blockers
- `critic.softConcerns`: structured soft concerns
- `critic.suggestedRubricItems`: structured rubric candidates
- `research.artifact`: saved researcher output artifact when a structured evidence packet was logged
- `research.confirmedFacts`: structured facts with citations
- `research.unresolvedQuestions`: unresolved questions
- `research.implications`: decision-relevant implications
- `research.conflicts`: structured conflicts or disagreements
- `tribunal.candidateMapArtifact`: parent-only unblinding map when blind packets were used
- `tribunal.summaryArtifact`: tribunal aggregation summary artifact
- `tribunal.summaryDataArtifact`: parseable tribunal summary companion
- `tribunal.judgePackets`: judge packet artifact paths
- `tribunal.aggregationMethod`: how the panel result was combined after unblinding
- `tribunal.result`: final panel result after unblinding
- `tribunal.note`: short aggregation note
- `tribunal.judgeVerdicts`: per-judge verdict artifact paths plus structured ranking, winner, rationale, and blockers when available
- `incumbentBefore`: path or label
- `incumbentAfter`: path or label
- `artifacts`: output files written this round
- `promotions`: promoted rubric items, checks, or acceptance criteria
- `degradedMode`: `true|false`
- `agentNames`: names of the agents that actually ran

The helper script handles the JSON structure for you.

When a round used blinded packets, prefer logging the tribunal structure explicitly instead of leaving it implicit in loose artifact names. `log_round.py` still supports explicit flags, but it can now also auto-discover structured judge / critic / researcher outputs and the tribunal companion from the artifact paths you pass.

Explicit flags remain available when you want to override or supplement auto-discovery:

- `--critic-output-artifact <path>` for a saved structured critic output
- `--researcher-output-artifact <path>` for a saved structured researcher output
- `--candidate-map-artifact <path>`
- `--tribunal-summary-artifact <path>`
- `--judge-verdict-artifact judge1=<path>` repeated per judge
- `--judge-panel-ranking "judge1=Candidate 2>Candidate 1>Candidate 3"` repeated per judge
- `--aggregation-method "<description>"`

If you pass `round-<n>-tribunal-summary.md` in the artifact list and the matching `round-<n>-tribunal-summary.json` companion exists, `log_round.py` will infer the companion automatically.

For judge, critic, or researcher outputs that are saved to disk for later aggregation, prefer the role schemas documented in [references/subagents.md](subagents.md) and validate them with:

```bash
python3 .agents/skills/autocatalyst/scripts/validate_structured_output.py --role judge --file /path/to/output.md
```

## Convergence

Stop when one of these becomes true:

- the convergence helper reports `decision = "stop"` because the incumbent survival streak reached `survivalTarget`
- benchmark gains flatten and the added complexity is no longer justified
- judges keep repeating the same minor feedback without changing the winner
- the user interrupts or redirects the task
- the artifact is good enough for handoff

The incumbent survival streak is computed automatically from logged rounds:

- `winner=A` with `status=keep` increments the streak
- `winner=B` or `winner=AB` with `status=promote` resets the streak
- other round outcomes do not advance the streak

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
