# Runbook: LLM Cost & Availability

## Context
- Provider: OpenRouter (deepseek/deepseek-chat default). LLM responses are
  cached (`ai/llm_cache` keyed by prompt+model); repeated identical analysis
  windows cost nothing.
- Keys live ONLY in `.env` (gitignored). Never in logs (httpx loggers are
  capped at WARNING for this reason).

## Checks
```bash
docker logs pmi-scheduler --since 1h | grep -i 'llm\|cache'
curl localhost:8001/ready            # shows llm provider status
```

## Cost control
- Scheduler generates analysis on a schedule; the cache dedupes repeated runs.
- If spend must be stopped: `docker compose stop scheduler` (analysis stops,
  everything else keeps running).
- To change model: set `LLM_MODEL` in `.env`, then
  `docker compose up -d --build quant scheduler`.

## Failure modes
- OpenRouter 401 → key invalid/expired; replace OPENROUTER_API_KEY in .env.
- OpenRouter 429/503 → analysis gracefully degrades to the last cached
  analysis; the UI shows the analysis age. No fabricated content is produced.
