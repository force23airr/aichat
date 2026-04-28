# aichat

Let your AI models collaborate from the terminal.

## Setup

1. Set API keys as environment variables (at least one):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   export OPENAI_API_KEY=sk-...
   export DEEPSEEK_API_KEY=sk-...
   ```

2. Install:
   ```bash
   pip install -e .
   ```

## Usage

```bash
aichat task "Create a 3-point plan to cut cloud costs" --starter claude --participants claude gpt
```

See the conversation unfold in your terminal. Use Ctrl+C to stop early, or add `--max-turns 6` to limit exchanges. Save the transcript with `--output plan.md`.

## Classification

Classify an existing transcript by epistemic type:

```bash
aichat classify haiku.md
```

This writes `haiku.md.classified.jsonl` and prints a summary of factual assertions, opinions, predictions, recommendations, hypotheticals, questions, and meta-commentary.
