# ADR 0006 — Who owns the presentation of settings

- **Status:** accepted
- **Date:** 2026-09-02
- **Plan item:** `4.0-E06a`
- **Follows:** `4.0-R04` (information architecture), `4.0-F08` (localisation), `4.0-B06` (settings behind an interface)
- **Enables:** `4.0-E06` (settings over the protocol), `4.0-F04` (pages)

## Context

That the core owns the settings **values** was settled by `4.0-B06`: the shell no longer reads the file, and `SettingsProvider` deliberately exposes only `get`, `set`, `save` and `transaction`. What was left open is whether the core also owns the **description of the form** — sections, order, labels, hints, which field is disabled while another is off.

The question is not academic. There are 48 settings across five storage groups, and `4.0-R04` gives the settings screen a designed shape: ten sections in one scrolling panel with pinned legends, chosen because an instrument is a front panel with sections rather than a cabinet with drawers. If the core describes the form, then every such decision has to be expressible in whatever vocabulary the description uses, and the shell's ability to redesign is capped by that vocabulary rather than by the design.

Three considerations settled it, and the first is the strongest because it was already decided elsewhere.

**Localisation is already split, and settings labels fall on the shell's side of that split.** `4.0-F08` records: interface strings live in the shell, Rina's own lines live in the core — otherwise her personality ends up smeared across two languages and two sets of files, which matters for RinaNeuro. A label like "Слова активации" is an interface string. A core that owned the form would own those labels, and the F08 decision would be quietly reversed by an implementation detail.

**Design decisions belong where design happens.** The ten sections of `R04` are not a property of the data; they are a claim about how a person settles down to configure a voice assistant. Deriving them from a core-side description would mean the core carries an opinion about screen layout, and every visual change would become a protocol change.

**But the core does know things the shell cannot re-derive.** Which values a field accepts. That `model_address` is meaningless while "answer with a model" is off. That an address outside `localhost` sends conversations to another machine — a warning only the core can produce, because only the core knows what that address is used for. Handing this to the shell means re-implementing core knowledge in another language, where it will drift.

So the line is not *form versus values*. It is **meaning versus presentation**.

## Decision

**The core owns meaning; the shell owns presentation.**

The core describes, per key: its type, default, allowed values or range, which other setting it depends on, whether it is secret (never logged, never shown in the clear), and whether changing it takes effect only after a restart. `settings.set` answers with a per-key verdict, using the error catalogue of `4.0-D05`, so "not accepted" and "accepted with a warning" are machine-readable rather than prose.

The shell owns labels, hints, section grouping, order, search, progressive disclosure, and every other question of how the panel looks and reads.

`settings.describe` therefore returns a schema and **no layout**, and says so explicitly rather than omitting the field: a missing key reads as "not implemented yet", while an explicit `"layout": null` reads as "this is not ours to describe", which is the actual state of affairs.

## Alternatives considered

**The core owns the form as well.** The tempting version: a declarative description, so the shell renders whatever the core sends and a new setting appears without touching C#. Rejected on three counts. It caps redesign at the expressiveness of the vocabulary — grouping, dependency, progressive disclosure and warnings all have to be invented up front, and the first thing the design asks for that the vocabulary cannot say becomes a protocol change. It contradicts `4.0-F08` by moving interface strings into the core. And it makes the settings screen the one screen in the application whose appearance is not decided where appearance is decided.

**Reuse the plugin page vocabulary (`4.0-H01`) for settings.** Attractive because that vocabulary has to exist anyway. Rejected, and the reason is worth recording because it looks like a missed opportunity: plugins are written by other people, who cannot ship XAML into our shell, so a declarative description is forced there — it is the price of letting strangers add pages. Our own settings screen is under no such constraint. Paying a cost without the reason that justifies it is not consistency, it is imitation.

**The shell owns everything, including validation.** Rejected: the shell would have to know which model names are valid and what makes an address local. That knowledge lives in the core, and a second copy in another language drifts from the first — silently, because a stale validation rule looks exactly like a correct one until it wrongly accepts something.

## Consequences

**Gained.** The settings screen is designed, not generated. `R04`'s ten sections can be rearranged without touching the protocol. Interface strings stay in one place, as `F08` requires. Validation stays where the knowledge is.

**Paid.** Adding a setting touches both sides: the key and its constraints in the core, the label and its section in the shell. This is the real cost of the decision and there is no version of it that is free.

**Constrained, with a rule that makes the cost visible instead of dangerous.** A shell that does not recognise a key must render it in a generic section rather than hide it. A hidden unknown key is the failure mode this decision would otherwise create: the core gains a setting, the shell is not updated, and the setting becomes unreachable without anyone noticing. Rendered plainly, it is merely ugly — and ugly gets fixed.

**Deferred.** If a future plugin wants to contribute settings rather than a page, it arrives through the plugin vocabulary of `4.0-H01`, not through this schema. Two mechanisms, because there are two situations: our settings are designed once by us, a plugin's settings are described by someone we will never meet.
