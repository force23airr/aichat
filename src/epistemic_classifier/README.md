# epistemic_classifier

Classifies AI-generated transcript sentences by epistemic type before downstream verification.

## API

```python
from epistemic_classifier import classify_sentence, classify_transcript

result = classify_sentence(
    sentence="The US GDP grew by 2.8% in Q4 2025.",
    prior_sentence=None,
    speaker=None,
)

results = classify_transcript("haiku.md")
```

`classify_transcript` parses the existing `aichat` transcript formats:

- live terminal lines like `[claude] ...`
- saved markdown turns like `## Turn 1 (claude)`

It segments prose, skips fenced code blocks and markdown headers, and treats bullets as individual sentences. Compound sentences joined by words like `and` or `but` are not split in v1; the classifier picks the dominant epistemic type.

## Configuration

Defaults:

- model: `claude-haiku-4-5-20251001`
- cache: `~/.epistemic_classifier/cache.db`
- logs: `~/.epistemic_classifier/classifications.jsonl`

Environment variables:

- `ANTHROPIC_API_KEY` for Claude models
- `OPENAI_API_KEY` for `gpt-*` or `openai:*` models
- `EPISTEMIC_CLASSIFIER_OPENAI_ENDPOINT` for OpenAI-compatible providers
- `EPISTEMIC_CLASSIFIER_OLLAMA_ENDPOINT` for `ollama:*` models
- `EPISTEMIC_CLASSIFIER_CACHE_DB` to override the SQLite cache path
- `EPISTEMIC_CLASSIFIER_LOG_PATH` to override structured log output

## CLI

```bash
aichat classify haiku.md
aichat classify haiku.md --model gpt-4o-mini
aichat classify haiku.md --model ollama:llama3
```

The command prints a summary table and writes `<transcript>.classified.jsonl`.

## Eval

```python
from epistemic_classifier.eval import run_eval

metrics = run_eval("tests/fixtures/eval_set_v1.jsonl")
```

The runner saves a full report to `eval_results/v1_<timestamp>.json`. The fixture included in this repo is a local v1 seed set; acceptance-threshold claims require a real model run and review of the error report.
