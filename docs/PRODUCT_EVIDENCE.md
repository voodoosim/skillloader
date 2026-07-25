# Gate 6 product evidence

## Accepted isolated live Codex comparison

On 2026-07-21, the versioned 12-task routing fixture was run once in each of
two invocation-scoped configurations, for 24 live Codex executions total:

- Client: Codex CLI `0.144.6`
- Model: `gpt-5.6-sol` through ChatGPT login
- Catalog: the 10 synthetic parity skills
- Eager mode: the complete catalog in invocation-scoped developer instructions
- SkillLoader mode: the bootstrap in developer instructions and exactly the
  `search_skills` and `load_skill` MCP tools
- User prompt: the same `Query: ...` text in each paired run
- Isolation: a temporary `HOME` and `CODEX_HOME`, an ephemeral symlink to the
  active Codex authentication file, `--ignore-user-config`, `--ephemeral`, a
  read-only sandbox, and a temporary working directory outside the repository
- Effective-prompt check: `codex debug prompt-input` was run in the isolated
  environment before every call; its hash was recorded and every call rejected
  injected `# AGENTS.md instructions`
- Sampling: one run per task and mode; temperature was left at the unreported
  Codex client default

The runner does not read or copy the authentication file contents and does not
modify user configuration. Reproduction command:

```bash
python3 -m pip install -r requirements-gate6.txt
GATE6_RESULTS="$(mktemp -d /tmp/skillloader-gate6-results.XXXXXX)"
python3 scripts/run_gate6_codex.py \
  --output-dir "$GATE6_RESULTS/run"
```

The runner requires a new output directory and refuses to overwrite recorded
evidence. `requirements-gate6.txt` pins the token estimator used by this run.

The runner scores original Codex events before redacting the stored evidence. It
records exact synthetic prompts, prompt hashes, redacted invocation arguments
and Codex JSONL events, MCP results, final structured responses, usage,
duration, and scores. Scores can be regenerated without another model call:

```bash
python3 scripts/run_gate6_codex.py \
  --rescore-dir bench/results/2026-07-21-codex-0.144.6-gate6-isolated
```

Rescoring validates the full recorded invocation shape, preserves the recorded
execution tasks, and permits scoring-only fixture changes only when task IDs and
model-visible queries are unchanged. Prior scoring hashes and each record's
exact current `scoring_task` are retained. It then regenerates the retained
final response, usage, estimates, and scores against the current fixture catalog. The
live calls were executed from uncommitted runner source. The
artifact records the execution runner SHA-256, current rescoring runner SHA-256,
fixture SHA-256, requirements SHA-256, and clean Go build-source hash. The exact
execution-runner source is no longer available after review fixes and was not in
base commit `782d2b3`; this is a clean-commit reproducibility limitation.

## Results

| Metric                                                        |          Eager | SkillLoader |
| ------------------------------------------------------------- | -------------: | ----------: |
| Executions completed                                          |          12/12 |       12/12 |
| Routing-fixture success                                       |          10/12 |       11/12 |
| Raw search top-1                                              | not applicable |        8/10 |
| Raw search top-5 recall                                       | not applicable |        9/10 |
| Final selection top-1                                         |           9/10 |        9/10 |
| No-load accuracy                                              |            1/2 |         2/2 |
| Incorrect-load runs                                           |           2/12 |        0/12 |
| Expected load count                                           |          10/12 |       11/12 |
| Required skill set with exact final instructions              |           9/10 |        9/10 |
| Runs copying every selected skill's final instruction exactly |          11/11 |         9/9 |
| Routing failures                                              |           0/12 |        0/12 |
| MCP/tool execution failures                                   | not applicable |        0/12 |
| Client-reported input tokens                                  |        152,353 |     522,331 |
| Client-reported uncached input tokens                         |        140,321 |     155,483 |
| Total wall time                                               |        87.149s |    194.094s |

For this small catalog, SkillLoader used 3.43 times the total input tokens and
1.11 times the uncached input tokens reported by Codex. It took 2.23 times the
wall time. Expressed through the benchmark's reduction formula, the results are
`-242.84%` total input reduction, `-10.81%` uncached input reduction, and
`-122.72%` duration reduction; these negative values mean increases.

The offline `tiktoken 0.13.0` `cl100k_base` estimate gives:

- eager developer instructions including the catalog: 711 tokens;
- SkillLoader developer instructions plus exact MCP schemas: 619 tokens;
- initial static overhead reduction: 12.94%;
- catalog block alone versus MCP schemas: 589 versus 457 tokens, or 22.41%.

These static estimates are not provider billing tokens. The client-reported turn
usage aggregates all model calls and includes cached input; both raw dimensions
are retained in `summary.json`.

## Observed quality failures

1. For `릴리스 노트 작성해줘`, eager selected `korean-router` and
   `release-notes` instead of the exact required set; SkillLoader returned no
   match. The current Korean query does not connect to the English-only release
   metadata through SkillLoader search.
2. Eager incorrectly selected `korean-router` for `서울 날씨 어때`; SkillLoader
   correctly returned no match and loaded nothing.

The security-gate query returned `docker-builder` as the raw search top-1, so
SkillLoader's raw search top-1 failed for that task. Codex still loaded and
applied the exact required set, `api-guardian` and `docker-builder`, with
`api-guardian` first in its final selection.

## Superseded evidence

`bench/results/2026-07-21-codex-0.144.6-gate6/` is retained as historical
evidence but is not an accepted eager-versus-SkillLoader product comparison.
An independent review reproduced that the host-level
`/home/vodo/.codex/AGENTS.md` entered its effective prompts despite
`--ignore-user-config`; the old runner neither isolated `HOME` nor recorded the
effective prompt. Its numbers are therefore confounded. It still records live
Codex stdio MCP calls, but product conclusions use only the `-isolated` result.

The task scoring fixture was strengthened after the superseded execution to
require exact selected skill sets. After the accepted isolated execution,
review also found that the regression query requested testing but the oracle
incorrectly required `release-notes`. The current scoring fixture requires only
`test-designer`. The recorded query, effective prompt, model output, usage, and
duration are unchanged; `environment.json` retains the execution fixture hash,
the current scoring hash, and prior scoring hashes separately.

## Conclusion and limits

## OpenCode warm-session token-cache check

On 2026-07-21, OpenCode `1.18.4` ran one cold search/load pair and one repeated
pair in the same session against the current local `skillloader` binary. The
second pair supplied `known_query_hash` and `known_content_sha256`:

| Measurement                         | Cold pair | Warm pair |
| ----------------------------------- | --------: | --------: |
| Tool payload characters             |     9,841 |       450 |
| OpenCode-reported step input tokens |    16,969 |       542 |
| `cached: true` responses            |       0/2 |       2/2 |

The observed tool-payload reduction was 95.43% for this one repeated scenario.
This is warm-session evidence, not a general provider billing reduction claim;
new sessions still pay the cold search/load cost, and broader repeated-task and
catalog-size measurements remain required.

Live Codex stdio compatibility, search/load execution, complete document
returns, and exact extraction of each selected skill's final instruction are
verified for this isolated fixture. The fixture does not verify that the model
followed the full document while completing a substantive task. SkillLoader
improved exact routing-fixture success by one run and
eliminated incorrect loads, but a positive token or latency benefit is not
verified; all three measured end-to-end cost dimensions were worse.

This evidence does not establish:

- task-completion quality beyond routing and final-instruction extraction;
- statistical stability beyond one run per task and mode;
- a real-catalog or large-catalog break-even point;
- cross-platform OpenCode behavior beyond the warm-session check below;
- provider-exact tokenization of the offline static layers;
- release-artifact or clean-room installation compatibility.

## Live Claude Code comparison

A Gate-6-equivalent isolated comparison for Claude Code CLI `2.1.212` is
recorded in `bench/results/2026-07-25-claude-code-2.1.212-gate6-isolated/`
and documented in `docs/BENCHMARK.md` under "Live Claude Code routing
evidence". It is the same 12-task fixture and 10-skill catalog as the Codex
comparison above, run with `scripts/run_gate6_claude_code.py`, and shows the
same direction (SkillLoader costs more at this small catalog size) plus a
Claude-Code-specific `ToolSearch` deferred-tool-resolution overhead that has
no Codex analogue. Anthropic's usage-accounting fields are not the same
shape as Codex's; the two clients' totals are not directly comparable to
each other, only to their own eager-mode run. The earlier
`bench/results/2026-07-25-claude-code-2.1.212-live-roundtrip/` directory
remains a plain stdio round-trip check, not a comparison, and is superseded
for comparison purposes by the `-gate6-isolated` directory.
