# Reconciliation eval report

24 labelled rows (14 from the sample statement, 10 synthetic).

| Matcher | Precision | Recall | Wrong matches | Exact outcome |
|---|---|---|---|---|
| Full (name + number + amount + date) | 100% | 100% | 0 | 24/24 |
| Baseline: name only | 39% | 50% | 11 | - |
| Baseline: amount only | 54% | 50% | 6 | - |

## Misses by the full matcher

None.
