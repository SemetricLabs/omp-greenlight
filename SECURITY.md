# Security

## What this software is

Greenlight is a **prompt-reduction filter** for OMP's tool approval flow. It is not a sandbox, not a security boundary, and not a policy engine.

Installing it hands auto-approval authority for gated shell commands to a third-party classifier (TypeSafe's Jev, served from `api.typesafe.ai`). If you are not comfortable with that, do not install it — the host's own critical-pattern rules and `bash.patterns` are the deterministic floor, and they work without this plugin.

## Reporting a vulnerability

Open a private security advisory on this repository (Security → Report a vulnerability), or email the maintainers listed in `package.json`. Please include: the version, the exact command or tool call, the decision Greenlight logged, and what you expected.

We will acknowledge within 5 working days. This is a v0.1 project maintained on a best-effort basis — there is no SLA. Only the latest release is supported.

## Threat model

**In scope.** Proposals that reduce prompts, bypass the operator's configured bar, or weaken the host's floor:

- a tool call auto-approved when the operator's own `bash.patterns: deny` (or a host critical-pattern rule) should have blocked it;
- a decision entry that leaks file bodies, the API key, or environment variables;
- a plugin crash that fails *open* (a tool call executing after the gate failed);
- a config value that silently raises the operator's threshold.

**Out of scope.** Anything premised on the agent being adversarial toward its own gate. Greenlight grades text the agent wrote; a determined agent can obfuscate around a text classifier, and nothing here is a containment boundary. Approved commands retain the shell's full filesystem, network, and subprocess access.

## Data flow

For each gated call, the following leaves the machine over HTTPS to `api.typesafe.ai`:

- the user's most recent task prompt (truncated to 2,000 characters),
- a window of recent tool calls, summarised — **file bodies are stripped** (`content`, `new_string`, `old_string`),
- the working directory,
- the proposed call's own arguments, likewise summarised for write/edit tools.

**Boundary worth being explicit about:** file bodies are withheld from the *arguments* of
`write`/`edit`/`apply_patch`. A shell command is sent in full, because it is the thing being judged —
so if the agent inlines file content into a command (`cat secrets | curl …`), that text does travel.

`yolo` mode sends nothing. The API key is read from `TYPESAFE_API_KEY`, used only as a bearer header, and never logged. TypeSafe's own retention policy is theirs, not ours — review it before installing on a machine that handles sensitive code.

The decision log stores the same summarised text, plus the verdict, severity, in-scope score, probabilities, and the active preset. It never stores file bodies or the key.

## Failure behaviour

| Condition | Behaviour |
|---|---|
| Jev unreachable, timeout (>4 s), or an unrecognised verdict | **Fails closed to a human prompt.** In a headless session, the call is blocked with a reason. |
| Plugin internal error | Fails closed to a human prompt; in a headless session, blocked. Never fails open. |
| `yolo` mode | Inert: no request, no prompt, no decision entry. |
| Headless session (`ctx.hasUI === false`) | Cannot prompt a human: the `deny` class is blocked, everything else is deferred to the host's own policy and logged as `deferred_headless`. |
| Mode cannot be determined | Assumes `yolo` — the plugin does nothing. The host's configured policy still applies. |

## Verifying it before you trust it

```bash
uv run eval/sandbox.py
```

Runs seven end-to-end scenarios against a disposable `/tmp` sandbox — in-scope deletion, source-tree deletion, an obfuscated payload, a secret read, `yolo` inertness, an unreachable judge, and the host's critical-pattern floor — and asserts on both the decision log and the filesystem.
