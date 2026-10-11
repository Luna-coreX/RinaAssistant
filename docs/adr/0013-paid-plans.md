# ADR 0013 — Paid plans: accounts and Pro arrive with Stable

- **Status:** accepted
- **Date:** 2026-10-11
- **Plan item:** `4.0-P01`
- **Builds on:** [ADR 0001](0001-license-and-contributions.md) (open core), `4.0-B08` (`FeatureProvider`)

## Context

The intent from before the beta was built: **the beta is free, Stable introduces accounts and subscriptions.** The architecture already assumed it — `FeatureProvider` exists so that a paid plan becomes a second implementation beside `CommunityFeatures` rather than checks scattered through the code, and `core/features.py` holds the vocabulary of capabilities that may be paid. The plan did not: its milestone table describes only `port` and `beta`, and its section "after the beta — decided by data" reads as if whether to charge at all were still open. This record closes that gap.

Three constraints are already fixed and public, on the site and in `ROADMAP.md`, and this decision has to keep them word for word:

- the local base stays free for good — voice pipeline, local model, finding and launching programs, reminders, timers, hotkeys, system actions with confirmation, history, aliases, settings, **base and own plugins**, the security journal;
- what becomes paid is **added**, preferably what costs money to run: a service on a server, a connector to a third-party service;
- the paid layer is protected by not being published, not by the licence (ADR 0001). A switch in the open core would be removed from the Apache-2.0 source in a minute.

## Decision

**Stable introduces accounts and one paid plan, Pro. Business comes later.**

- **Community** — everything that exists today, free, open, **without an account**. Signing in is needed only for what is paid.
- **Pro** in Stable, from the existing vocabulary:
  - `sync` — end-to-end encrypted synchronisation of settings, commands and scenarios between devices. The server and storage cost money; this is the plainest fit for the public promise.
  - `workflow_packs` — ready-made scenario packs. Content, not a cut from the base: scenarios a person builds in the constructor stay free.
  - one or two `connector.*` to third-party services that the free plugins do not cover.
- **Business** — later: deployment, central policies and allow-lists, audit.

The Pro capabilities beyond these are expected to grow during Stable; each addition is checked against the free-for-good list above before it is planned.

**Paid code is closed and separate.** Each Pro capability is a closed module — a plugin in its own process under the existing protocol (`4.0-H07`) or a server service — delivered after activation. The open core only asks `has_feature()`; it contains no paid code and no way to unlock any.

**Connectors run on the person's computer.** A connector is a closed plugin that talks to the service's API directly from the device, keeping its tokens in the plugin secret store (`4.0-H11`). The service's data does not pass through our servers. Where a service's OAuth requires a client secret in the token exchange, a small endpoint on our server performs that exchange and nothing else; the privacy policy names it.

**The free GitHub plugin (`4.0-H14`) stays free**, as a base plugin. `connector.github` is removed from the vocabulary of capabilities that may be paid.

## Not decided here

- **The seller's legal form.** A sole proprietorship (ИП) is being considered and is not settled. It blocks the public offer (`4.0-S06`), the payment provider and the account server's operator details, and is the first task of the block (`4.0-P01`).
- **The payment provider.** It depends on the seller's jurisdiction, and the provider most people would reach for may not accept that jurisdiction. Chosen in `4.0-P01` together with the legal form.
- **Which connectors and at what price.** Chosen with the user conversations (`4.0b-D04`) and the beta's data, not ahead of them.

## Alternatives considered

**Stable stays free, paid plans in 4.1 after the data.** Proposed in discussion on 2026-10-11 and set aside: it contradicts the intent the architecture was built for, and the data from the conversations still decides *what* is paid and *for how much* — only not *whether*.

**Paid features as switches in the open core.** Rejected by ADR 0001's reasoning: under Apache-2.0 anyone can build the core without the switch.

## Consequences

- Stable gains a block of its own, `4.0-P`, the size of the update block: accounts, licences and device activation, `ProFeatures`, billing, delivery of closed modules, the server, and the first Pro capabilities.
- `4.0-S05` (consent to personal data processing) and `4.0-S06` (public offer) stop being conditional: an account is personal data, and a subscription is a sale.
- The account server is commercial: it cannot run on a plan that forbids commercial use. Its hosting is chosen in `4.0-P10`.
- The privacy policy and the licence agreement get new editions with Stable: the account, what the server keeps, the token-exchange endpoint, and the paid part.
