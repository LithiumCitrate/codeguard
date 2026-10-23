# Changelog

All notable changes to CodeGuard are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
abides by semantic versioning.

## [0.4.0] - 2026-10-24

### Added

- **First-run LLM setup in the workbench**: an optional dialog collects any
  OpenAI-compatible base URL + API key, lists models via `/models` (the key is
  verified live before saving) and stores the choice in the local workspace
  (`llm_config.json`, git-ignored, permission 0600 where the OS allows). The
  key is never returned to the browser (masked form only), never embedded in
  exports, and clearing it restores the fully offline tool.
- **AI file reading** (`POST /api/interpret`): uploaded/pasted code gets a
  deterministic licence-marker extraction (SPDX ids, copyright lines, vendored
  hints, source URLs — same input, same output, works with no key) plus an
  optional LLM reading of what the file does and what to check next.
- **AI scan summary and grounded Q&A** (`POST /api/assist`): after a scan the
  model writes an executive summary and answers questions strictly from the
  evidence digest (no source code stored); when no model is configured the
  summary degrades to a deterministic digest text and Q&A states it needs a
  model.
- **AI plain-language licence notes** (`POST /api/license/explain`): the rule
  engine's verdict is explained for non-specialists; the verdict itself is
  never generated or altered by the model.
- Optional per-scan checkbox "审查中用大模型重写处置建议": when enabled and a
  model is configured, finding explanations come from the LLM and the receipt's
  `ai_usage` honestly records `openai-compatible`, the model name and
  `external_calls: true`; disabled (default) keeps the byte-reproducible
  offline template.
- 19 new offline tests (126 total) covering settings hygiene and masking,
  model-list failures, prompt construction against a loopback stub, endpoint
  token gating, and the no-key-leak guarantee.

### Changed

- `llm.py` grew a small settings/marker module (`save/load/clear`, validation,
  `list_models`, `extract_license_markers`); `OpenAICompatProvider` gained a
  generic `chat()` used by all four interpretation prompts, each with the same
  guardrails (only interpret given material, never legal advice, ≤400 chars).
- The workbench hero and "方法与边界" copy now state exactly what leaves the
  machine: nothing by default, and only user-triggered AI actions send text to
  the configured endpoint.
- Version 0.4.0.

## [0.3.0] - 2026-10-21

### Changed

- **Workbench redesigned** as a console: dark command bar with three sections
  (`#review` / `#license` / `#about`, now real deep links with back-button
  support), a risk dial that reads the last scan (S0–S4 sector, confidence,
  span/coverage/verbatim gauges), corpus and engine panels fed from
  `/api/health`, and export buttons that appear only once a receipt exists.
  Every figure on the page comes from the live index or the scan result.
- Results are ledger rows instead of bordered cards: cut-corner risk tags
  (accent fill for S3/S4), hairline-separated findings, and the same evidence
  payload as before. Light and dark themes, `prefers-reduced-motion`, and a
  44px touch target on every control.
- **Saira (SIL OFL 1.1) is now bundled** as the Latin interface face
  (`static/fonts/Saira.ttf` plus `Saira-OFL.txt`); Chinese stays on the system
  sans. The font is served from the local package only - the workbench still
  loads no external resource (CSP `default-src 'self'`).
- The workbench's "方法与边界" page no longer repeats the AI-usage paragraph;
  the disclosure remains in README §6, the technical report, the resource list
  and every exported receipt (`ai_usage`).
- Version 0.3.0.

## [0.2.1] - 2026-10-21

### Added

- **Real-leakage evaluation** (`scripts/eval_model_leak.py`): scores the gate on
  47 genuine GPT-4o regurgitation cases published with LiCoEval (ICSE 2025,
  arXiv:2408.02487, AGPL-3.0-or-later).  All 4,187 licence-tagged reference
  originals are indexed as distractors, so attribution is earned rather than
  given.  Evidence: `submission/evidence/model-leak-20261021.*` plus a
  two-person annotation worksheet.  The dataset is fetched by URL + SHA-256 and
  never redistributed.
- **Elicitation harness** (`scripts/eval_model_elicitation.py`,
  `scripts/elicitation_prompts.jsonl`): turns raw assistant answers into a
  labelled manifest for the product index.  The first pilot (6 answers) matched
  nothing in our own copyleft corpus and is reported as a negative pilot.

### Fixed

- `license_intel.resolve_spdx` ignored case and underscores, so lower-case SPDX
  ids from third-party inventories (`mpl-2.0`, `gpl-2.0-only`, `zlib`, `isc`)
  fell through to UNKNOWN and downgraded real copyleft files to review items.
  Resolution now folds spellings onto profiled ids and records the step as
  `case-fold` in the licence origin.  Measured on the 4,187-file LiCoEval
  reference pool: unresolved licences dropped from 309 to 2 (`cc-by-sa-4.0`,
  `cecill-2.1`).
- **`LGPL-3.0-only` (and the other version-suffixed LGPL ids) never blocked.**
  `analyze()` graded whatever SPDX id the corpus manifest recorded, and
  `PROFILES` only held `LGPL-2.1`/`LGPL-3.0`, so every glances file
  (`LGPL-3.0-only`, 70 files in the shipped corpus) resolved to family
  `unknown` -> status `unknown` -> **S2 review instead of S3/S4 blocking**.
  Added profiles for `LGPL-2.1-only`, `LGPL-2.1-or-later`, `LGPL-3.0-only`,
  `LGPL-3.0-or-later`, two `LGPL-3.0*` vs `GPL-2.0-only` conflict pairs, and a
  `graded_id()` fallback that re-runs the resolution chain for any id we have no
  profile for.  Measured: the mutation benchmark is unchanged (98.96% detect,
  100% blocking recall, 0/9 negatives), and `scripts/demo_gate.py --package
  glances` now exits 1 (S3) instead of 0.
- `normalize._number_bucket` raised `OverflowError` on `1e999` and
  `ValueError`-free non-finite/oversized literals, aborting an entire index
  build.  Such literals now bucket by spelling length.

### Changed

- `scripts/demo_gate.py` picked the first corpus file `os.walk` happened to
  return, so the documented "exit code 1" demo silently became a pass on
  machines where a 65-line stub came first.  Candidates are now sorted and the
  file with the most top-level code wins; paramiko/mercurial/glances all block.
- `scripts/validate_sbom.py` now also validates SARIF 2.1.0 against the OASIS
  schema, through the CLI path, and writes `submission/evidence/web-demo.sarif.json`.
  Previously only the CycloneDX side was reproducible from the repository.
- Version 0.2.1; Windows EXE and both release ZIPs rebuilt from this source
  (`CodeGuard-Windows-x64.zip` 46.50 MB, `CodeGuard-Source.zip` 1.28 MB) and
  re-verified with `scripts/smoke_app.py` in a relocated Unicode path.

- **Corpus is now version pinned.** `codeguard corpus` fetched whatever PyPI
  called latest, so a fresh checkout silently rebuilt a different corpus from
  the one every published number was measured on.  Versions are pinned in
  `src/codeguard/data/corpus_pins.json` (the 20 packages of the released
  evidence), a pin that cannot be honoured logs `PIN MISS` instead of falling
  back quietly, and `--latest` opts out explicitly.  The manifest records the
  policy and the pins it used.
- `DEFAULT_PACKAGES` was missing **mercurial** (19 of the 20 shipped packages),
  which is the GPL-2.0-or-later source behind the flagship
  `feature_flags.provenance.json` demo - a reviewer could not reproduce it from
  a clean clone.
- Two new licence profiles: `EPL-1.0` (weak/module copyleft, patent grant) and
  `BSL-1.0` (permissive), plus an explicit `EPL-1.0` vs `GPL-2.0-only`
  incompatibility.  The trove classifier used to map EPL-1.0 onto EPL-2.0,
  changing the licence id; on the 4,187-file reference pool this took unresolved
  licences from 309 to 2 (`cc-by-sa-4.0`, `cecill-2.1`).
- Version 0.2.1.

Offline tests: 107.

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
