# Open decisions

Team decisions the code is waiting on. Until each is made, the code uses a clearly marked placeholder
(`"placeholder": true` in the API). Settled ones move to the "Decided" list in `ml_llm_plan.md`.

## Readiness score

| Decision | Placeholder today | Where it lives |
|---|---|---|
| What a "normal" night should score | 50, with 10 points per standard deviation from your usual | `server/app/readiness/scoring.py` |
| Low / Moderate / Ready cut-offs | Low below 40, Ready from 70 | `server/app/readiness/scoring.py` |
| Minimum data before a score is shown | At least 7 usable nights in the baseline (`BASELINE_MIN_NIGHTS`), and at least one z-score that night | `preprocessing/layer1/config.py`, `scoring.py` |
| Weight of sleep against HRV and resting HR | All five inputs (HRV, resting HR, sleep time, efficiency, fragmentation) count equally | `scoring.py` |
| Whether a short night should force Low | A night under 3 hours gets no score (status `short_sleep`), and is kept out of the baselines | `scoring.py`, `preprocessing/layer1/quality.py` |
| How much sweat data (Layer 3) can move the score | Not used yet. Proposed cap: ±5 points | Future readiness model |
| "Your usual" range | Baseline mean ± 1 standard deviation | `server/app/readiness/usual.py` |

The trained readiness model will replace the first, fourth and sixth rows. The team still has to agree what
the model may and may not do (for example the cut-offs and the Layer 3 cap) before it ships.

## Later

- Illness signals (respiratory rate, wrist temperature): when to start collecting them, and how the warning
  banner should read.
- Wording rules for the LLM explanation, beyond "only cite inputs whose Last night row isn't Usual".
