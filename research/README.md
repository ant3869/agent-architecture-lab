# Research

What is known about building agent systems, with sources, and how it maps onto this repository.

| File | Contents |
|---|---|
| [`topics.md`](topics.md) | Findings for fourteen engineering topics: what the literature and documentation establish, and what this repository implements and measures for each |
| [`frameworks.md`](frameworks.md) | LangGraph, OpenAI Agents SDK, CrewAI, AutoGen / Microsoft Agent Framework, MCP, A2A and the durable-execution engines: factual profiles, a comparison table, and the differences that change an engineering decision |
| [`SOURCES.md`](SOURCES.md) | The bibliography with verification status (generated from [`sources.toml`](sources.toml)) |
| [`verification.json`](verification.json) | Output of the last automated source check |

## How the research was done

1. Primary sources only for claims about a system: its own documentation, specification or repository, and for papers the arXiv record. Secondary write-ups were used to find things, never as the citation.
2. Each documentation page or specification cited was fetched and the specific passage read; the passage is summarised in the `note` field of the source entry and the entry is marked `content`. Paper titles, authors and dates were confirmed against the arXiv API, and quantitative claims are quoted from abstracts.
3. Entries that were only checked for reachability are marked `reachable`; anything that could not be fetched is marked `unverified`.
4. `python scripts/verify_sources.py` repeats the reachability and title checks and rewrites `verification.json`.

## Reading the documents

- Numbers attributed to a paper or vendor are their measurements on their benchmarks.
- Numbers introduced with "Measured here" come from this repository's simulator and are bound to [`../experiments/RESULTS.md`](../experiments/RESULTS.md); conditions and limitations are stated there.
- No third-party framework was executed for this research. Comparisons with frameworks describe their documented behaviour.
- Fast-moving facts (release status, protocol revisions) are stated as of the date in `verification.json`.
