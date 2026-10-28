# Eval run: baseline-final-PARTIAL

Overall: 60/60 (100.0%)

## Config

- llm: openai/gpt-oss-20b
- temperature: 0.1
- embedding_model: BAAI/bge-m3
- chunk_size: 900
- chunk_overlap: 120
- top_k: 4
- min_relevance: 0.35
- stale_after_days: 365

## By category

| Category | Passed | N | % |
|---|---|---|---|
| access_confirm | 1 | 1 | 100.0 |
| conflict | 4 | 4 | 100.0 |
| escalate | 10 | 10 | 100.0 |
| fact | 25 | 25 | 100.0 |
| multi | 7 | 7 | 100.0 |
| no_false_escalation | 3 | 3 | 100.0 |
| unanswerable | 10 | 10 | 100.0 |

## Secondary metrics

| Metric | % | N |
|---|---|---|
| retrieval_hit_rate | 100.0 | 39 |
| citation_rate | 100.0 | 39 |
| correct_refusal_rate | 100.0 | 10 |
| correct_escalation_rate | 100.0 | 10 |
| confirmation_card_rate | 100.0 | 1 |
| false_escalation_rate | 0.0 | 39 |

## Failures (0)
