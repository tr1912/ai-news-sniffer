# AI News Sniffer

The source subsystem collects a curated, configurable set of public AI-news
sources. It does not ask a model to discover or enable production sources.

## Source modes

- `light`: 12 core official/research sources, at most 20 AI candidates.
- `balanced`: 25 sources, at most 30 candidates; this is the default.
- `full`: all 35 sources, at most 40 AI candidates by default.

Set the default with `active_profile` in `config/sources.yaml`. A source with
`enabled: false` or a disabled source group remains off in every mode.

## Local inspection

```bash
python -m pip install -e ".[dev]"
ai-news-sniffer sources list --profile light
ai-news-sniffer sources candidates
```

## Intentional live checks

The regular test suite does not access live websites. Use one of these commands
when you intentionally want network access:

```bash
ai-news-sniffer sources test openai-news
ai-news-sniffer sources audit --profile balanced
```

A successful live audit clears a runtime auto-pause; it never changes
`config/sources.yaml` or commits to `main`.

## One-run overrides

```bash
ai-news-sniffer sources audit \
  --profile full \
  --include-sources openai-news,anthropic-news \
  --exclude-sources anthropic-news \
  --max-ai-candidates 10
```

`include_sources` only narrows sources that are already enabled and belong to
the selected profile. `exclude_sources` is applied last.

The manual workflow uses `0` for `max_ai_candidates` to select the profile
default: 20 for `light`, 30 for `balanced`, and 40 for `full`.

## Cost controls

RSS/API/HTML collection itself consumes no model tokens. Before a later
editorial call, `config/app.yaml` limits candidate count, excerpt characters per
item, and total prompt characters. The recorded token value is an estimate;
character limits are the hard enforcement mechanism.

## Candidate sources

Unknown upstream domains are written to
`runtime-data/candidate-sources.json` with `enabled: false`. Approve one only by
reviewing its ownership and access policy, adding a complete entry to
`config/sources.yaml`, and committing that change.
