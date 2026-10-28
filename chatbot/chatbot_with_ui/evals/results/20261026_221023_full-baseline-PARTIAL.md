# Eval run: full-baseline-PARTIAL

Overall: 35/35 (100.0%)

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
| conflict | 3 | 3 | 100.0 |
| fact | 25 | 25 | 100.0 |
| multi | 7 | 7 | 100.0 |

## Secondary metrics

| Metric | % | N |
|---|---|---|
| retrieval_hit_rate | 100.0 | 35 |
| citation_rate | 100.0 | 35 |
| false_escalation_rate | 0.0 | 35 |

## Failures (0)
