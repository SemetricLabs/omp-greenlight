# Changelog

All notable changes to this project. Per `SECURITY.md`, any change to what data leaves the
machine, to verdict semantics, or to fail-open/fail-closed behaviour is called out as breaking.

## v0.1.0 — 2026-09-19

First release.

- Gates `bash`, `eval`, `write`, `edit`, `apply_patch`, `delete`, `move`; grades each call with
  TypeSafe's Jev (`jev-latest`) and suppresses the approval prompt on a confident `allow`.
- Risk dial: `conservative` / `default` / `permissive` / `aggressive` presets, or an explicit
  `autoApproveMinP` / `severityCeiling`. Operator-owned: the plugin never tunes its own threshold.
- State carries the task, a bounded tool-history window (~1,258 input tokens), the working
  directory, and the proposed call. The agent's own prose is deliberately excluded.
- Decision log per session (`/greenlight-decisions`), optional JSONL sink via `GREENLIGHT_LOG`.
- `yolo` mode is a complete no-op: zero API calls.
- Fail-closed on an unreachable model, a timeout, an unrecognised verdict, or an internal error.
- Measured: 40.9% of approval prompts removed on 1,013 real tool calls; 0 of 94 must-not-run
  corpus rows auto-approved at the default bar; ~310 ms p50 per gated call.

### Known limitations

- Not a sandbox or a security boundary. Installing it delegates shell auto-approval authority for
  gated calls to a third-party model.
- Headless sessions cannot prompt a human, so only the `deny` class is blocked there; a `review`
  verdict follows the configured policy.
- File bodies are withheld from `write`/`edit` arguments, but shell command text is sent in full.
- The 140-row corpus is the only labelled safety evidence, and it is small and self-authored.
