# Roadmap

## Why keep going

Most map tools tell you what's there. This one tells you what a place *feels* like — turning OSM tags into H3-cell "vibe" text via a local LLM. That's a genuinely different question than the rest of this portfolio's OSM work asks, and it's already staged cleanly enough (area → features → cells → vibe → KML) that finishing it is mostly about proving the idea generalizes, not rebuilding the pipeline.

## What it opens up

GPX mode already lets a real run ground-truth the generated vibes cell by cell. Once comparing or merging vibe maps across areas works, the question changes from "what does this place feel like" to "where else feels like this" — turning a description tool into a discovery tool: find unexplored parts of a city that match the vibe of somewhere you already love.

## Capability this builds

Making numeric signals legible as language — the H3-cell-to-LLM-text pattern here is a reusable way to turn structured data into something a human actually reads and trusts, useful anywhere else in this portfolio that currently just outputs a CSV.

---

## Prior notes

# Roadmap

A staged OSM pipeline that clips an area, extracts and categorizes map features, aggregates them into H3 cells, generates LLM "walking vibe" text per cell (via local Ollama), and renders the result as color-coded KML.

## Near-term

- Add CI to run the existing test suite on push.
- Each run writes to its own directory under `DATA_DIR` — a natural next step given the design is already staged around H3 cells is comparing or merging vibe maps across multiple areas/cities.
