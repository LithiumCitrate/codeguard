# Changelog

All notable changes to CodeGuard are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
abides by semantic versioning.

## [0.2.0] - 2026-10-20

### Added

- **External evaluation harness** (`evaluate.py`, `codeguard eval`): JSONL
  manifests with `clean` / `copied` samples, false-block rate, attribution and
  top-1 source accuracy, latency percentiles, and a one-sided exact
  Clopper-Pearson upper bound. The report never embeds submitted source text.
- **HumanEval clean-negative evidence** (`scripts/eval_humaneval.py`): 164
  independent implementations, 0 blocking false positives (95% one-sided upper
  bound 1.81%), one non-blocking S1 observation. Dataset is fetched by URL +
  SHA-256 and is not redistributed.
- **Real GitHub project evaluation** (`scripts/eval_realworld.py`): 10 projects
  (requests/flask/fastapi/httpx/poetry/pip/setuptools/pytest/sqlmap/mitmproxy),
  12 scan sets including pip/setuptools `_vendor`, 447 sampled files, 320
  findings (S0 259 / S1 43 / S2 18), 0 blocking findings and 50 real vendoring
  hits. Repositories are shallow-cloned into the gitignored workspace and are
  not redistributed.
- **Real-world regression fix**: a vendored wheel CLI matched a GPL mercurial
  CLI on six generic argparse spans (22% coverage, 5 verbatim tokens,
  confidence 0.671) and was falsely blocked. Structural corroboration now
  requires a 10-token verbatim floor and the confidence threshold is 0.75; the
  case is downgraded to S2. Mutation benchmark remains 99% detection with 100%
  blocking recall.
- **Query-line mapping fix**: `Finding.matched_query_lines` was populated from
  upstream source line numbers. It now uses the query span lines, so SARIF and
  evidence locations point at the scanned file. Regression test uses a long
  source with a short query excerpt.
- **SARIF 2.1.0 output** (`report.to_sarif`, `scan --format sarif`,
  `gate --sarif`) with stable rule IDs, query/source locations and partial
  fingerprints for GitHub Code Scanning.
- **GitHub Code Scanning integration**: workflow now uploads self-scan and PR
  diff SARIF; `docs/INTEGRATIONS.md` documents CI, pre-commit and caching.
- **Evaluation docs** (`docs/EVALUATION.md`) and 20 new offline tests covering
  the external harness, upper bound and SARIF contract.

### Changed

- `report.TOOL_VERSION` now follows `codeguard.__version__`.
- README, benchmark docs and submission evidence reference the external
  clean-negative result and its limits.

## [0.1.1] - 2026-10-11

### Added

- Local web workbench, Windows x64 application package, portable corpus
  restore, CycloneDX validation and end-to-end evidence files.

## [0.1.0] - 2026-10-04

First public release, prepared for the 2026 AI+Open-Source track of the
Global Campus AI Algorithm Competition.

### Added

- **Multi-layer code fingerprint** (`normalize.py`, `fingerprint.py`): four
  invariance views over one token stream - literal, abstract (per-window
  aliasing), role, and relational edges - plus a syntax-independent fallback
  lexer so diff hunks, truncated fragments and non-Python sources still
  produce usable spans.
- **Compact LSH index** (`index.py`, `minhash.py`, `cms.py`): Mersenne-prime
  permutation MinHash, b-bit (8-bit) compression with bias correction, 32-bit
  band keys, `CGIDX2` zlib container. 328 bytes of payload per span; the index
  stores no source text.
- **Two-stage verification** (`evidence.py`): exact per-layer Jaccard,
  IDF-weighted containment backed by a Count-Min sketch, and the longest
  verbatim token run found by binary searching n-gram sets.
- **SPDX licence-obligation engine** (`license_intel.py`): ~28 licence
  profiles including the domestic MulanPSL-2.0 and `LicenseRef-Proprietary`,
  scope/trigger/obligation model, explicit conflict table, resolution chain
  (PEP 639 expression -> legacy field -> trove classifier -> source header ->
  UNKNOWN, never defaulting to permissive).
- **Explainable judge model** (`score.py`): dependency-free logistic
  regression trained by SGD, Mann-Whitney AUC, Youden's J threshold,
  group-split-by-file evaluation.
- **Reproducible benchmark** (`benchmark.py`, `mutations.py`,
  `data/negatives/`): 8 deterministic code-laundering mutations, clean-room
  negative controls, hash-based baselines and a 10-row ablation table.
- **CLI and CI gate** (`cli.py`): `corpus` / `index` / `scan` / `gate` /
  `licenses` / `model` / `benchmark` / `doctor`, with the gate exit-code
  contract 0/1/2, GitHub Actions workflow and a `pre-commit` hook.
- **Open outputs** (`report.py`): `codeguard.provenance/v1` receipt,
  CycloneDX 1.6 SBOM with evidence occurrences, and a self-contained offline
  HTML report that always carries the AI-usage disclosure.
- **Optional LLM narration** (`llm.py`): offline template provider by default;
  an OpenAI-compatible provider only activates through explicit environment
  variables and falls back automatically. Narrative text never changes a
  verdict or a risk level.

## [Unreleased]

### Added

- **Corpus-availability guard.** Exact verification re-reads the original corpus
  text, so a missing corpus previously produced an empty scan and the gate exited
  0 - "could not check" printed exactly like "checked and clean". `scan` and
  `gate` now check `FingerprintIndex.corpus_health()` first and exit 2;
  `--allow-partial-corpus` continues but records the caveat in the report `notes`.
  `doctor` prints the readable/total document count.
- **Blocking requires corroboration.** `adjudicate.corroborates()` grades a
  licence conflict S3/S4 only when spans cover ≥15% of the file, or a verbatim
  run reaches 20 tokens, or the file-level confidence reaches 0.65; otherwise it
  is an S2 advisory and the downgrade is explained in the report. Measured over
  200 real corpus files (worst-case proprietary target licence), per-file false
  blocking dropped from 3.5% to 0% while the renamed+reformatted+commented+
  dead-code demo still blocks.
- **Risk grading now uses confidence** as well as status and usage, so a
  0.5-probability conflict no longer looks as severe as a 0.99 one.
- `codeguard benchmark --fp-study N`: cross-package false-positive study run
  through the production scanner, separating vendored duplicates (same filename,
  true positives) from unexpected matches, with risk distribution and per-file
  blocking rate. `benchmark.md` gained a gate-blocking column.
- `--corroborate-coverage/--corroborate-verbatim/--corroborate-confidence` on
  `scan` and `gate`.
- `benchmark --min-chars N` to include smaller source files in a benchmark run
  (needed to exercise the pipeline on tiny fixtures, and useful for snippet-level
  corpora).
- `benchmark` gained a **threshold-sensitivity / pair-level IDF ablation** table:
  for each candidate threshold it reports how many pairs pass with and without IDF
  weighting, split into pairs against the true origin document and against
  everything else. It reuses the features already cached during verification, so it
  costs no extra scanning.
- `scripts/false_block_control.py`: the control run behind the "3.5% -> 0% false
  blocking" claim - the same 200-file cross-package study with the corroboration
  requirement switched off, so the comparison is reproducible without editing source.
- stdout/stderr are reconfigured to UTF-8 with replacement on entry, so Chinese
  output survives a cp936 Windows console instead of crashing mid-scan.
- AGPL §13 is now a first-class *obligation* for `network_service` usage,
  including the same-licence case, and `AGPL -> GPL` relicensing is derived by
  `compare()` instead of a conflict-table row.
- Reviewer-facing documentation: `docs/TUTORIAL.md`, `docs/DESIGN.md`,
  `docs/BENCHMARK.md`, `scripts/reproduce.sh` (corpus -> index -> benchmark ->
  tests -> gate self-check) and `scripts/demo_gate.py` (builds a "the model
  rewrote a copyleft helper" PR diff from the local corpus and runs the gate).
- `submission/`: the competition deliverables, with team fields left as `xxx`.
  Includes the nine-chapter technical report, the eight-column third-party resource
  list, a storyboard plus a word-for-word narration script for the demo video,
  a per-slide speaker script, an evidence bundle (provenance JSON / CycloneDX SBOM /
  offline HTML / benchmark table) and **`答辩演示.html`, a self-contained 17-slide
  defence deck** (no external resources; keyboard navigation, toggleable speaker
  notes, print-to-PDF stylesheet).
- `scripts/make_demo_sample.py` (materialises the demo subject inside the gitignored
  workspace, so corpus-derived fragments never enter the Apache-2.0 repository) and
  `scripts/record_demo.sh` (nine banner-separated screens for turn-key recording).

### Fixed

- **IDF was inert in every loaded index.** `CountMin.from_base64` restored the
  counter table but not `total`, so after any save/load `idf_weight()` evaluated
  `log(max(0, 2*df)/df) = log 2` for *every* shingle - a constant. Weighted
  containment therefore degenerated to plain containment in production, while the
  benchmark (which uses a freshly built in-memory index) trained the judge on the
  real weighted feature. Same feature, two values: silent train/serve skew plus a
  headline mechanism that did nothing at scan time. `cms_total` is now persisted,
  the container version is bumped to 1.2 (old indexes are rejected rather than
  quietly degraded), and a regression test asserts weights survive the round trip.
- `relation_edges` treated a definition header as ending at the *body's* first
  bracket, so every call/argument edge inside a `def` was silently dropped. L4
  fingerprints therefore changed; the index and the whole benchmark were rebuilt.
- `rename` sorted tokens by `(line, -col)` while iterating in reverse, which is
  ascending column order: earlier replacements overwrote later ones and produced
  unparsable files.
- `comment_inject` hard-coded four-space indentation, so injecting a docstring
  into a 2/3-space file (typically after `reformat`) made the *compound* mutant
  unparsable and measured the fallback lexer instead of the fingerprint. It now
  reuses the file's own indent unit, derived as the smallest positive indent.
- `rank_auc` unpacked `(score, index)` pairs as `(index, score)` and raised
  `TypeError` on the first real call.
- `gate --diff` treated the path argument as the diff body and scanned the
  filename. `--diff` now accepts a path, `-`, or inline text.
- Usage and environment errors printed a message to `sys.exit()`, which the
  shell reports as exit code 1; they now exit with the documented code 2, and
  the `licenses` verdict propagates to the exit code (1 = incompatible).
- `FingerprintIndex.load` turned `active_layers` into a list, so a reloaded
  index used different parameter keys than the one that was saved.
- Licence expressions were split on lower-case `or`/`and`, turning
  `GPL v2 or later` into `GPL-2.0-only`; only SPDX operators split now, and
  short metadata forms (`gpl3`, `lgpl2.1`, `Apache 2`, `Proprietary`,
  `BSD 2-Clause`, `MulanPSL`) resolve properly.
- `report.to_html` passed four arguments to a three-placeholder footer.
- `hooks/pre-commit` read `$?` inside the `else` branch of an `if`, where it had
  already been reset by the condition, so a blocked commit reported exit code 0
  and an environment error was presented as a licence violation.
- Module docstrings no longer claim comments are preserved in the verbatim view
  (they are stripped from every layer, which is what stops injected commentary
  from inflating a match).

### Remaining work

- Incremental index updates (append/evict documents without a full rebuild).
- Java / JavaScript / C normalisers, which unlock cross-language corpora.
- Licence-obligation knowledge-base expansion with per-clause citations.
