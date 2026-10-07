# Model routing

Last checked: 2026-10. Model names change often: update the table, not the logic.

| Tier | Model (pick the newest available) | Use for |
|---|---|---|
| FLASH | Gemini 3.8 Flash (fallback: 3.7, then 3.6 Flash) | profile, report, trend, anomalies, formatting the final answer from verdicts |
| PRO | Gemini 3.1 Pro | diagnosis across several sources, attribution reconciliation, cohort/LTV, budget reallocation, strategy memos, writing narrative.json in audit mode, editing scripts |

## Rule of thumb
- Mechanical (run a command, read a table): FLASH.
- Judgement (why did it happen, what should we change, which source is right): PRO.
- Never send raw data to either tier. Send only `out/summary.md` and the top rows of `out/*.csv`.

## Audit mode split
- FLASH: A1-A3 (pull, run engine, data-quality gate), A5 (build), A6 (self-check), Step L logging.
- PRO: A4 (narrative.json) and any script change. PRO reads facts.md only, never raw data.

## Escalate FLASH to PRO when
- `route` says PRO.
- The same step failed twice (wrong column mapping, template not followed).
- Numbers from two sources disagree by more than 15% and the cause is not obvious.
- The user asks "why" or "what should I do" about more than one channel at once.

## Cost pattern
FLASH does Steps 2-3 (most tokens, no judgement). PRO reads only the small summary for Steps 4-5. This keeps PRO usage to a few thousand tokens per analysis.
