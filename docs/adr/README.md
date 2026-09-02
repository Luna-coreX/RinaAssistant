# Architecture Decision Records

Short documents recording decisions that are expensive to reverse: what was decided, what else was considered, and why. One file per decision, numbered, never rewritten — a decision that turns out wrong gets a new record that supersedes the old one, so the reasoning at the time stays readable.

A decision belongs here when undoing it would mean rewriting rather than editing: a licence, a transport, a UI framework, where a responsibility lives. Ordinary choices belong in the code and its comments.

| № | Decision | Status | Plan item |
|---|---|---|---|
| [0001](0001-license-and-contributions.md) | Licence and contribution model — Apache-2.0, no CLA | accepted | `4.0-S01` |
| [0002](0002-ipc-transport.md) | Transport between shell and core — named pipe, hosted by the shell | accepted | `4.0-D01` |
| [0003](0003-voice-identity.md) | What "her own voice" means — a synthesised speaker vector | accepted | `V-01` |
| [0004](0004-versioning-and-compatibility.md) | Versioning — four independent versions; the protocol decides compatibility | accepted | `4.0-U01` |
| [0005](0005-control-library.md) | Control library — none; own styles over standard WPF | accepted | `4.0-F01b` |
| [0006](0006-settings-ownership.md) | Settings — the core owns meaning, the shell owns presentation | accepted | `4.0-E06a` |

## Decided but not yet written up

These were settled in discussion and are recorded in [`../ROADMAP.md`](../ROADMAP.md); they need their own records before the work starts.

| Decision | Plan item |
|---|---|
| Shell UI framework — WPF | `4.0-F01` |
| Plugins run in their own process, in 4.0 | `4.0-H07` |
| 4.0 split into a frozen port and a feature-bearing beta | `4.0-S03` |

## Open, and blocking work

Nothing is open that blocks work in progress.
