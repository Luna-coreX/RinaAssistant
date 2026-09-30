# ADR 0001 — Licence and contribution model

- **Status:** accepted
- **Date:** 2026-09-01
- **Plan item:** `4.0-S01`
- **Supersedes:** the MIT licence used up to and including 3.1.0

## Context

The project is about to accept outside contributions for the first time. Until now every one of its 31 commits was written by a single person, who therefore holds all rights and can change the licence unilaterally. **That window closes the moment a third party's code is merged**, because relicensing would then require every contributor's consent — or the removal of their work. This is the only decision in the whole plan where delay forecloses options rather than merely postponing them, which is why it is scheduled first.

The product plan is open core with a commercial layer: the desktop application stays open, while the licensing backend, billing, and paid connectors stay closed. Three facts follow from that and shape the decision.

**No licence protects the paid features.** The only thing that protects them is not publishing their source. The licence question therefore concerns the free desktop base alone, and choosing a restrictive licence in the hope of protecting revenue would trade adoption for nothing.

**Copyleft and the plugin system conflict — but only until 4.0.** Today a plugin is loaded into the core process, where it is plausibly a derivative work; under a copyleft licence, plugin authors would have to open their plugins on the same terms. That would foreclose the third-party plugin ecosystem the project is deliberately building. Task `4.0-H07` moves plugins into their own process behind a documented protocol, which is the configuration where copyleft conventionally does not reach across. So copyleft becomes viable at 4.0 and is actively harmful before it.

**A network copyleft licence has almost nothing to offer here.** The AGPL clause is triggered by running software as a hosted service. This is a desktop application; the benefit is close to zero while the cost in corporate adoption is real.

## Decision

**Apache License 2.0, with no Contributor Licence Agreement.**

Contributions are accepted under the inbound-equals-outbound rule that the licence itself provides in section 5: a contribution intentionally submitted for inclusion is licensed under the same terms, unless its author explicitly states otherwise. That clause is the reason no separate CLA is needed — it does the same job without adding paperwork to every pull request.

The `LICENSE` file holds the canonical Apache-2.0 text verbatim (SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`). Copyright attribution lives in `NOTICE`.

## Alternatives considered

**Staying on MIT.** The status quo, and a perfectly respectable licence. Rejected because it is silent on two things this project specifically needs: patents, and its own name. Apache-2.0 costs nothing in adoption or compatibility relative to MIT and closes both gaps.

**GPL-3.0 with a CLA.** Would prevent a closed commercial fork, which MIT and Apache-2.0 both permit. Rejected on balance: part of the corporate audience avoids the GPL; a CLA adds friction to every contribution and administrative work for a solo maintainer; and the protection is narrower than it looks, since the paid layer is protected by not being published rather than by the licence.

**Dual licensing, GPL plus a commercial exception.** The model that makes sense when selling licence exceptions is part of the business plan. It is not part of this one — the planned revenue comes from extended features, integrations and services, not from exemptions. It would also require full ownership of all rights, meaning a CLA or assignment agreement in place before the first contribution, plus legal preparation. Rejected as solving a problem the project does not have.

## Consequences

**Gained.** An explicit patent grant from every contributor, which MIT does not provide. Explicit trademark protection under section 6: a fork inherits the code but not the right to call itself Rina — which matters given the plan to build a brand and a commercial tier around it. Contributions arrive under known terms with no paperwork.

**Not gained.** Nothing prevents a closed-source commercial fork of the free base. This was accepted knowingly: forks rarely outrun a maintained upstream, and the commercially valuable parts are protected by remaining unpublished, not by the licence.

**Not retroactive.** Releases up to and including 3.1.0 were distributed under MIT, and anyone holding a copy keeps their MIT rights to it. The change applies going forward; it does not and cannot revoke what was already granted.

**Per-file headers are deliberately omitted.** Apache-2.0 recommends a boilerplate header in each source file but does not require one. Adding it to every module would add noise to files whose comments are otherwise load-bearing explanation. `LICENSE` and `NOTICE` at the repository root are sufficient. Revisit if the project ever vendors its code into another codebase, where per-file headers do real work.

**Follow-up.** `CONTRIBUTING.md` states the inbound rule. `4.0b-C05` adds the remaining community documents. Should dual licensing ever become a genuine business need, it will require a CLA from every contributor accumulated by then — the cost of that path grows with each merged pull request, and that is the accepted trade.
