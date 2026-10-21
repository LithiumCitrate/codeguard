# Security Policy

CodeGuard is an offline, local-first licence-provenance tool. It does not execute
submitted code, does not upload source, and binds its web workbench to loopback.
That reduces the attack surface but does not remove it: parsers, the local HTTP
service and report rendering still process untrusted input.

## Supported versions

| Version | Supported |
|---|---|
| 0.2.x | yes |
| 0.1.x | no (upgrade to 0.2.x) |

## Reporting a vulnerability

Please do not open a public issue for a security report. Use this repository's
private vulnerability reporting (Security tab → "Report a vulnerability").
Include:

- affected version / commit,
- a minimal input or reproduction command,
- impact (crash, hang, path traversal, XSS, token leak, etc.),
- whether the issue is already public.

We aim to acknowledge within 7 days and to publish a fix or mitigation with a
clear credit line unless you ask to remain anonymous. There is no bug bounty.

## In scope

- denial of service through pathological source input or an oversized request;
- path traversal or reading files outside the workspace/corpus root;
- leakage of the loopback session token or submitted source;
- XSS or external-resource injection in generated HTML/SARIF;
- report or index corruption that turns "could not check" into a pass;
- dependency or packaging supply-chain issues in the release artifacts.

## Out of scope

- legal conclusions or the accuracy of a licence interpretation;
- detection quality on code outside the published benchmark/evidence;
- vulnerabilities in upstream corpus packages (report them upstream; CodeGuard
  only reads those files and does not link or execute them);
- findings caused by modifying the local corpus or index outside the documented
  verification commands.

## Safe defaults

- the web service listens on `127.0.0.1` only and requires a per-session token;
- submitted code is never executed;
- the scan reports a corpus-integrity failure with exit code 2 rather than a
  silent clean result;
- external LLM narration is off unless explicitly configured, and never changes
  risk levels or licence conclusions.
