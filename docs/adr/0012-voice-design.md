# ADR 0012 — How her own voice is made

- **Status:** proposed
- **Date:** 2026-09-22
- **Plan item:** `V-03`
- **Supersedes:** [ADR 0003](0003-voice-identity.md)
- **Determines:** what `V-04` chooses between, and what the bench measures from here

## Context

ADR 0003 decided that Rina's voice would be a synthesised speaker vector: a timbre belonging to no real person, obtained by interpolating inside a model's speaker-embedding space. The goal it set has not changed, and this record does not revisit it — a voice with no consent problem, no licence, no recurring cost, and an honest answer to "whose voice is this".

What has changed is what is known about the means. ADR 0003 attached a constraint to the decision: `V-03` may only shortlist models that expose a speaker embedding and permit synthesising or interpolating a vector. `V-03` ran that constraint to the end.

**Three models were measured, and the constraint eliminated all of them.** A multi-speaker Russian VITS renders a voice from a vector, but its speaker table has two rows: every point on the line between them — including the line extended past both ends — came back, to an independent verifier, as one of the two speakers. CosyVoice2 has a populated speaker space and a standard encoder, but no working path from a vector alone: asked to speak from one, it babbled to the length limit, and it babbled equally when handed the exact embedding of a real speaker, which is what proved the path rather than the interpolation was at fault. XTTS v2 does everything the constraint asks, with documented interpolation between speakers, and cannot be used: its weights are under a non-commercial licence and Coqui Inc. closed in January 2024, so there is nobody left to buy an exception from. FireRedTTS2 and Scenema Audio keep no speaker vector at all.

The pattern is not three unlucky models. The speech field of 2026 builds zero-shot cloning from reference audio, and a speaker vector that can be synthesised is increasingly not a thing these models have.

**The constraint also shaped the search, and hid the answer.** Both the plan's candidate list and its rebuild looked for models that expose a speaker embedding, because that is how ADR 0003 phrased the requirement. Voice design — generating a new voice from a natural-language description — exposes no embedding at all, and was therefore invisible to both lists while solving the same problem more directly.

## Decision

**Rina's voice is designed from a natural-language description, and the recording it produces is the voice.**

The voice is generated once from a description and a seed. The resulting audio file is the canonical artefact; everything Rina says afterwards is synthesised from that file as a reference. The person speaking it never existed, so no consent is owed to anybody — the question does not arise rather than being answered.

The first voice is `assets/voice/rina-voice-v1.wav`, made with VoxCPM2 (Apache-2.0) from the description *"A young woman, soft gentle voice, slightly high pitch, calm even pace"* at seed 20260923. The recipe is recorded beside the file; the file, not the recipe, is canonical, because a model version change devalues the recipe and leaves the file untouched.

Both conditions ADR 0003 attached to its decision are carried over and are part of this one.

**The artefact is project property and is stored as such.** Now literally: a wav file in the repository, versioned, alongside the emblem.

**Distance from real speakers is verified, not assumed.** Measured against eight real speakers with `tools/voice_identity.py`, on a scale where different people reach 0.537 and the same person scores about 0.856: the designed voice sits at most 0.278 from its nearest real speaker. It is further from every one of them than they are from each other.

**A voice specified only by a description is not stable and must not be used that way.** Consecutive utterances generated from the same description drift to 0.258 — below the level at which two unrelated people resemble each other. Pinned by its own recording, the same voice holds at 0.758 across seven utterances. The recording is what makes the identity continuous, and that is the reason it, rather than the description, is the artefact.

## Alternatives considered

**Speaker-embedding interpolation**, the decision this record supersedes. Not rejected on principle — it was measured and does not work with the models available in 2026. The two that render from a vector fail for unrelated reasons, and the one that satisfies the requirement fully is closed by its licence. If a model appears that renders faithfully from an interpolatable vector, this is worth revisiting: a vector is a smaller and more tractable artefact than a recording.

**Cloning a consenting voice actor.** Unchanged from ADR 0003: legitimate, rejected on cost and ownership, and still available as a fallback. Voice design weakens the case for it rather than closing it — the timbre would be the actor's, licensed rather than owned, and now there is a path where it is neither.

**Training on an own dataset.** Unchanged: the only fully model-portable answer, deferred behind the same trigger. The trigger's wording in ADR 0003 assumed the voice was tied to one model's embedding space; see the consequences below, where that assumption no longer holds in the same way.

**The maintainer's own voice.** Unchanged, and rejected for the same product reason.

## Consequences

**Gained.** A voice with no consent question at any point, under a licence that permits commercial use, reproducible exactly — the same seed returns a byte-identical file — and audibly a person. Two languages come with it: English program names inside Russian speech are pronounced as English rather than transliterated, and an entirely English sentence holds the timbre as well as Russian sentences hold it between themselves.

**The cost named in ADR 0003 is largely removed, and this is the most consequential part.** That record called out one real price: the voice would live in one model's embedding space, replacing the engine in 5.0 would change the voice, and for a product whose stated differentiator is continuity of personality, that mattered. Storing the voice as **audio** rather than as a vector removes most of that. A recording is what every zero-shot system takes as input, so the same file can be handed to a different engine and asked for the same person. The identity stops being a property of one model.

The trigger ADR 0003 named — record a dataset and train when the voice becomes an identity worth protecting — therefore becomes less urgent rather than more. It stays on the books as the fully portable answer.

**Paid.** The timbre wanders more than a real voice does. Across seven utterances it ranged 0.675 to 0.901 where the same person scores about 0.856: recognisably one person, and not as steady as one. Whether a longer reference narrows this is the obvious next measurement.

**Paid, and unresolved.** The engine is 4.7 GB and wants a graphics card. On the development machine — an AMD card, so no CUDA — synthesis runs at an RTF near 19: three seconds of speech cost a minute. Nothing here says how this ships to a user's computer, and that question belongs to `V-04` and `5.0-A06` rather than to this record.

**Constrained, differently.** `V-03` and `V-04` no longer need to shortlist only models that expose a speaker vector. The criterion becomes whether a model can take a reference recording and keep the person across utterances — which is what most of the field is built to do, and which is safe here precisely because the person in the recording does not exist.

**A note on method, since it cost the track two runs.** The requirement in ADR 0003 was phrased as a property of the model rather than as the goal, and the search inherited the phrasing. A constraint written into a decision becomes the shape of every later search, and the thing it excludes stops being visible. Where the goal can be stated without naming a mechanism, it should be.
