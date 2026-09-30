# ADR 0003 — What "her own voice" means

- **Status:** accepted
- **Date:** 2026-09-01
- **Plan item:** `V-01`
- **Determines:** the whole voice track — what the bench measures (`V-02`), which models qualify (`V-03`), and whether a dataset is needed at all (`V-05`, `V-06`)

## Context

Rina speaks. Until now she has borrowed whatever voice the installed engine offered — a system voice, a Microsoft neural voice, a Google one. None of them is hers, and every one of them ties her identity to a service. The voice track exists to give her one that is.

"Her own voice" can mean three different things, and the difference is not aesthetic. It decides what has to be recorded, what can be claimed, and what happens when the model underneath changes.

**Cloning an existing voice** is the fastest path: six to twenty seconds of reference audio and current models produce a convincing match. The question is whose voice. Cloning a real person without their agreement takes a biometric identity that is not ours to take, and doing it inside a product whose entire position is that the user controls their own data would be self-refuting. A hired voice actor solves the ethics with a contract and money, but the timbre stays theirs — licensed, not owned. Cloning the maintainer's own voice is ethically trivial and free, but then Rina speaks with her author's voice, which sits badly against a separate name and the feminine forms her replies already use.

**Speaker-embedding interpolation** synthesises a new speaker vector rather than copying one. The resulting timbre belongs to nobody: there is no person to consent, no contract, and an honest answer to "whose voice is this". It costs nothing and needs no recordings.

**Training on an own dataset** gives the most control and is the only option that survives a change of model, because the data is ours and can be used to train whatever comes next. It also needs hours of recorded speech with phonetic coverage of Russian and emotion labelling — and still needs a person willing to record it, which returns to the consent question with the answer already obtained.

## Decision

**Speaker-embedding interpolation.** Rina's voice is a synthesised speaker vector that corresponds to no real person.

Two conditions are part of the decision, not implementation detail:

**The vector is project property and is stored as such.** It is exported to a file, versioned, and treated like any other identity asset alongside the emblem. A voice that exists only inside a running model is a voice that can be lost by reinstalling something.

**Distance from real speakers is verified, not assumed.** Interpolating inside an embedding space can land close to a training speaker. Before the vector is adopted, its nearest-neighbour distance to the model's known speakers is measured and recorded. "Belongs to nobody" is a claim, and a claim needs a check.

## Alternatives considered

**Cloning a real person without consent.** Rejected outright, and not on balance: it is not a trade this project makes. It is also the one option whose downside is other people's.

**Cloning a consenting voice actor.** A legitimate path, rejected for now on cost and ownership. It stays available if interpolation cannot reach the quality bar the bench sets — the fallback is a contract, not a compromise.

**The maintainer's own voice.** Ethically clean and free, rejected on product grounds: Rina has her own name and her replies are written in the feminine; speaking with the author's voice would collapse a distinction the product deliberately maintains.

**Training on an own dataset now.** Not rejected — deferred. It is the only model-portable answer, and it becomes the upgrade path rather than the starting point, because it costs months before there is any voice at all.

## Consequences

**Gained.** A voice with no consent problem, no licence, no recurring cost, and an honest provenance. No dataset needed to start, so the track can produce something audible early rather than after a recording campaign.

**Paid — and this is the real cost.** The voice lives in one model's embedding space. Replacing the engine in 5.0 changes the voice, and Rina's identity would shift with it. That matters more here than in most products, because RinaNeuro's stated differentiator is continuity of personality, and a character whose voice changes with a dependency upgrade has less of it.

The consequence is accepted with a named trigger rather than hoped away: **when the voice becomes an identity worth protecting, the project records a dataset and trains, so the voice changes once, deliberately, instead of whenever the engine is upgraded.** Until that point, the model choice in `V-03` and `V-04` is also a voice-stability choice, and should be weighed as one.

**Constrained.** `V-03` may only shortlist models that expose speaker embeddings and permit synthesising or interpolating a vector. A model that clones only from reference audio, however good it sounds, does not satisfy this decision.

**Made unnecessary for now.** `V-05` (dataset protocol) and `V-06` (dataset collection) are not on the path to a first voice. They move behind the trigger above and stop blocking the track.
