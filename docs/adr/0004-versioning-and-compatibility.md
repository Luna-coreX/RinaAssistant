# ADR 0004 — Versioning and compatibility

- **Status:** accepted
- **Date:** 2026-09-01
- **Plan item:** `4.0-U01`
- **Enables:** the whole update system (`4.0-U02`…`U13`), and `4.0-D03` (handshake)
- **Related:** [ADR 0002](0002-ipc-transport.md), [protocol specification](../protocol/PROTOCOL-v1.md)

## Context

After the split there is no longer one thing with one version. The shell and the core ship as separate artefacts, can be updated separately, and can be rolled back separately. Something has to decide whether a given pair is allowed to run together, and that decision has to be answerable before either part is downloaded, and again when they meet.

The strategy document that prompted this work proposed carrying `min_core_version` / `max_core_version` in release metadata and checking those ranges at update time. The protocol specification, written separately, decided compatibility by exchanging protocol versions at handshake. Both cannot be the authority. Choosing one, and saying what the other is for, is the substance of this record.

There is also a version the source material did not separate at all: the on-disk data. Settings, commands, history and reminders already carry `CONFIG_VERSION`, currently 2. Rolling the core back to a build that predates a schema change is a different question from whether two processes can talk, and conflating them produces a rollback feature that corrupts data while reporting success.

## Decision

**Four independent versions, each answering one question.**

| Version | Question it answers | Form |
|---|---|---|
| **Protocol** | can these two processes talk? | single integer, no minor |
| **Shell** | which build of the window is this? | `MAJOR.MINOR.PATCH` |
| **Core** | which build of the brain is this? | `MAJOR.MINOR.PATCH` |
| **Data schema** | can this build read what is on disk? | integer, existing `CONFIG_VERSION` |

### Runtime compatibility is decided by the protocol, and by nothing else

Each side declares the set of protocol versions it implements. They are compatible if the sets intersect; the highest common version is used. The shell does not care what core *version* it is talking to, and the core does not care about the shell's. They care what it speaks.

Version ranges cannot be the runtime authority because they encode a prediction. `max_core_version: "4.99.99"` is a guess made at build time about software that does not exist yet, and it is wrong the moment a later core changes something. A declared protocol set is not a prediction: it is a statement about what the code in front of you actually implements.

**The protocol has no minor version.** Every additive change — a new method, a new event, a new optional field, a new enum value — is covered by capability negotiation, which the handshake already performs. The version increments only for a change that breaks a side implementing the previous version: removing or renaming a field, changing its type, changing what an existing value means, or making an optional field required.

### Version ranges survive, demoted, in update metadata

`min_core_version` / `max_core_version` stay in release metadata, but as an **optimisation, not a rule**: they let the updater avoid downloading a pair that would fail the handshake anyway. A wrong range costs a pointless download and a clear error. A wrong range trusted as authority would cost a refused update that would in fact have worked.

Where the two disagree, the handshake wins, because it is the one looking at the real thing.

### Staged updates: the shell moves first

When the protocol version increments, both parts need to change — but not at the same instant, or updating would require a synchronised swap that cannot be made safe.

**The shell must implement the previous protocol version for one release beyond its introduction.** A shell speaking `{1, 2}` runs happily with a core speaking `{1}`, so the shell can be updated first and the core follows whenever it is convenient. The core carries no such obligation: it can drop old versions freely, because the shell supervises it and is therefore the part that can be relied upon to be current.

One release of overlap, not two. Longer support windows are cheap to promise and expensive to keep, and the shell is not distributed independently of this project.

### Incompatibility is reported, never silent

No common protocol version is a normal outcome, not a crash. The shell — which starts the core, and therefore has somewhere to display it — states which part is too old and offers to update it. `4.0-D03` requires exactly this: an old shell meeting a new core produces an explanation, not a mysterious failure.

### Rollback is bounded by data, not by process compatibility

A core may be rolled back only to a build whose data schema version is greater than or equal to the one currently on disk. Going back past a schema migration means the older build cannot read what the newer one wrote.

Where that is the case, the choice is put to the user in those terms — data written after the upgrade will be lost — and the rollback is refused by default rather than performed with a warning. This is why the data schema is a version of its own: without it, "can I roll back" gets answered by looking at process compatibility, which does not know anything about the file on disk.

## Consequences

**Gained.** Compatibility that cannot go stale, because it is negotiated rather than predicted. Independent update of either part with no coordination. A rollback rule that is checkable rather than hopeful.

**Paid.** The shell carries the previous protocol version for one release — real code, kept working, for a case that will rarely be exercised. Conformance tests (`4.0-D16`) must therefore include an old-protocol shell against a current core, or the obligation is decorative.

**Constrained.** `4.0-U02` metadata carries protocol version sets alongside the numeric ranges, and `4.0-U03` checks the sets. `4.0-U12` (rollback) gains the data-schema check as a precondition rather than an afterthought.

**Corrected.** The protocol specification's compatibility section stands as written; the strategy document's range-based scheme is demoted to a download hint. This record supersedes it on that point.
