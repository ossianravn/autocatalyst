# Evidence Modes

## Judge-first

Use when the artifact is mostly judged by usefulness, clarity, originality, feasibility, taste, or strategic fit.

Typical tasks:

- concept descriptions
- proposals
- wireframes
- naming systems
- early specs
- product narratives

Recommended tribunal:

1. source / citation sanity check when research is involved
2. three blind judges
3. incumbent wins close calls

Good rubric dimensions:

- task fit
- clarity
- specificity
- feasibility
- distinctiveness without gimmicks
- usefulness for the next team that must act on it

## Benchmark-first

Use when the task already has a trusted hard signal.

Typical tasks:

- code performance changes
- build fixes
- pass-rate improvements
- cost reductions
- latency or throughput optimization
- bug fixes with strong regression coverage

Recommended tribunal:

1. hard checks
2. benchmark
3. optional blind judging only when code quality tradeoffs matter

## Hybrid

Use when the task mixes hard and soft evaluation.

Typical tasks:

- specs that must be both correct and persuasive
- research-informed implementation plans
- code changes where maintainability still matters
- feature design plus a partial implementation
- prompt systems that need both correctness and usability

Recommended tribunal:

1. eliminate candidates that fail hard checks
2. compare trusted metrics
3. use blind judges for the remaining ambiguity
4. keep `A` when evidence is not decisive

## Selector for ambiguous tasks

When the mode is unclear, spawn `autocatalyst_selector` with the anchor packet only.

Ask it to decide:

- whether success is mainly soft / human-judged
- whether a trusted benchmark captures most of what matters
- whether the task genuinely mixes hard and soft evaluation

Interpretation:

- mostly soft / human-consumed → `judge-first`
- mostly hard / machine-validated → `benchmark-first`
- mixed or under-specified → `hybrid`

## Tie-breaking rules

- favor the incumbent when evidence is weak or close
- favor the challenger when hard evidence is clearly better and soft quality does not collapse
- favor `AB` when `A` has essential strengths and `B` fixes real weaknesses without adding new major flaws

## Promotion thresholds

Avoid promotion on tiny, noisy, or purely aesthetic changes unless the user explicitly wants polish rounds.

A promotion should usually satisfy at least one:

- materially stronger against the rubric
- materially stronger benchmark or pass rate
- clearer path to implementation or adoption
- clearer communication to the target audience
- fewer serious open risks
