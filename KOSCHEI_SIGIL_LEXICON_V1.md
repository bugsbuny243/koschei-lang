# Koschei Sigil Lexicon v1

Status: canonical semantic design document

This document defines the deep meaning of Koschei's native sigils. A sigil is not a decorative keyword, an alias for a foreign language construct, or a renamed library call. It is a compact semantic root whose meaning expands across identity, authority, evidence, execution, recovery, visibility, lifecycle and composition.

The implementation remains responsible for enforcing these meanings. Prose in this document must never be treated as permission to weaken a fail-closed runtime rule.

## 1. `ka`

### Core identity

`ka` is the semantic root of admitted existence.

It does not merely mean "create", "start", "new", "constructor", or "initialize". Those are implementation-shaped verbs. `ka` answers a deeper question: **what may enter a Koschei universe as a recognized thing, under which identity, with which initial authority, and on the strength of what evidence?**

A thing that has not crossed `ka` may physically exist as bytes, memory, a process, a module, a request, an artifact or an external observation, but Koschei does not yet recognize it as an authoritative participant.

### Birth law

`ka` establishes a genesis boundary. Crossing that boundary requires an identity claim and evidence sufficient to bind the claim to the admitted object. Admission creates recognition; it does not create privilege.

Therefore the default product of `ka` is **recognized existence with zero ambient authority**.

No object receives network, disk, process, environment, signing, recovery, visibility or other privileged authority merely because it was born or discovered.

### Identity law

Identity under `ka` is not a display name. It is a canonical relation between the admitted object and the evidence used to recognize it.

Aliases may change. Locations may change. Representations may change. Serialization may change. A module may move. A process may restart. None of those events may silently manufacture a new canonical identity or merge two identities.

When identity cannot be established without ambiguity, `ka` fails closed.

### Integrity law

Admission must bind the relevant integrity material before authority is derived from the object. Depending on the object this can include source identity, artifact digest, policy digest, activation-plan digest, lineage evidence or another canonical proof selected by the subsystem.

An object whose integrity changes after admission is not automatically the same trusted object. The changed object must be re-evaluated under the applicable lifecycle rules.

### Zero-authority law

`ka` can establish that something is known. It cannot establish that the thing is allowed to perform privileged effects.

This separation is fundamental:

`existence != authority`

`identity != authority`

`integrity != authority`

`recognition != authority`

Authority belongs to the `vor` domain and must be explicitly derived and narrowed there.

### Time and epoch law

A `ka` admission belongs to an epoch. Evidence from an older epoch may be used as historical lineage where policy permits, but old-epoch authority cannot become current authority merely because the identity resembles a previously admitted identity.

After containment and rebirth, the new epoch must establish fresh admitted state. Rebirth is not resurrection of old privilege.

### Evidence law

`ka` requires evidence for state-changing admission. The evidence must be bound to what was admitted, not merely to a nearby event.

Evidence that proves "something existed" but cannot prove **which canonical object** existed is insufficient for authoritative admission.

### Failure behavior

`ka` fails closed on ambiguous identity, missing required integrity material, conflicting genesis evidence, invalid epoch, non-canonical admission order, or an attempt to smuggle authority into birth.

Failure must not degrade into a permissive anonymous identity.

### Attack behavior

Under hostile input, `ka` prefers refusal over inference. An attacker may create unlimited candidate names, paths, encodings, wrappers or representations; these do not force Koschei to admit unlimited identities.

Repeated malformed admission attempts must not widen authority, weaken identity requirements or teach the attacker hidden semantic state through privileged error differences.

### Relationship with `vor`

`ka + vor` creates the **Genesis Authority Seal**.

Authority must descend from an admitted identity. If the identity or its required integrity binding becomes invalid, authority derived from that admission cannot remain silently valid.

`vor` may narrow authority; it may never rewrite the genesis evidence that made the authority eligible to exist.

### Relationship with `shi`

`ka + shi` creates **Identity Evidence Binding**.

Observation becomes authoritative evidence only when Koschei can bind the observation to the correct admitted identity and epoch. Evidence cannot float between identities because their names, locations or payloads look similar.

### Relationship with `thal`

`ka + thal` means containment and recovery preserve identity history without preserving privilege.

A recovered object may prove continuity with an older identity, but recovery does not automatically restore old authority. A new epoch must derive authority again according to current policy.

### Relationship with `nur`

`ka + nur` separates canonical identity from externally visible identity.

Koschei may rotate aliases, compartments, routes or observable representations without changing the canonical identity. Conversely, learning an external alias does not reveal the full canonical identity graph or grant authority over it.

### Whole-universe role

When `ka / vor / shi / thal / nur` are composed, `ka` is the genesis anchor. It must precede privileged activation of the other domains. The universe may observe unknown material before admission, but it may not treat unknown material as a privileged participant.

### What `ka` must never become

`ka` must never become a renamed `class`, `new`, `let`, constructor, account-creation API, authentication shortcut, implicit capability mint, global registry insertion or permission grant.

If a future implementation makes `ka` equivalent to a familiar language keyword with cosmetic syntax, that implementation violates this lexicon.

### Minimal invariant set

1. No ambient authority at birth.
2. Canonical identity must be evidence-bound.
3. Required integrity is bound before privileged authority derivation.
4. Ambiguous admission fails closed.
5. Identity and authority remain separate domains.
6. Admission is epoch-bound.
7. Rebirth does not resurrect old authority.
8. Alias changes cannot silently rewrite canonical identity.
9. Observation alone cannot manufacture admission.
10. `ka` cannot be used as an authority-escalation primitive.

---

## 2. `vor`

### Core identity

`vor` is the semantic root of bounded power.

It answers: **what may act, on what, through which capability, producing which effect, for how long, and under which non-escalation constraints?**

`vor` is not "permission = true". It is the physics that prevents authority from becoming ambient.

### Authority law

Authority must be explicit, typed, narrowable and attributable to an admitted origin. Possession of data, visibility, identity or evidence does not imply possession of authority.

### Narrowing law

Root authority is not an everyday execution object. It exists to derive narrower capabilities. A narrowed capability cannot recreate its parent root merely by calling another method or crossing a recovery boundary.

### Effect law

Privileged effects must correspond to canonical capability operations. Network, disk, environment, process and future privileged domains use canonical effect identities rather than subsystem-specific aliases.

### Non-escalation law

Composition, recovery, observation and visibility changes cannot create authority absent from the input authority set. Authority may be reduced, expired, contained or re-derived under a new epoch; it may not emerge from convenience.

### Whole-universe role

`vor` supplies controlled action to identities admitted by `ka`, leaves evidence to `shi`, remains bounded during `thal`, and stays separate from what `nur` reveals.

### Minimal invariant set

1. No privileged effect without explicit authority.
2. Root authority narrows before ordinary use.
3. Narrowed authority cannot widen itself.
4. Effect identity must match the capability operation.
5. Recovery cannot invent authority.
6. Visibility cannot imply authority.
7. Authority is epoch-sensitive.
8. Unknown capability operations fail closed.

---

## 3. `shi`

### Core identity

`shi` is the semantic root of witnessed reality.

It answers: **what happened, who or what observed it, how independently it was observed, which identity and authority produced it, and whether the evidence is strong enough to influence state?**

`shi` is not logging. Logs can lie, disappear, conflict or be emitted by the actor they claim to prove.

### Evidence law

Claims and evidence are separate. A privileged actor cannot make its own claim final merely by emitting a success message.

### Lineage law

Evidence carries lineage to the relevant identity, authority, effect, epoch and prior evidence where required. Detached evidence cannot authorize a different event.

### Conflict law

Conflicting authoritative observations do not get averaged into truth. Where the required proof cannot be established, the dependent transition fails closed.

### Independence law

Security-critical conclusions may require independent observation or quorum rather than self-attestation by the component being judged.

### Whole-universe role

`shi` makes the universe capable of proving rather than merely claiming. It binds `ka` identity to `vor` action, gates `thal` recovery and survives `nur` visibility rotation without requiring total disclosure.

### Minimal invariant set

1. Claim is not proof.
2. Evidence must bind to identity and epoch.
3. Evidence cannot widen authority.
4. Conflicting required evidence blocks finality.
5. Critical self-attestation alone is insufficient where independence is required.
6. Evidence lineage survives permitted representation changes.

---

## 4. `thal`

### Core identity

`thal` is the semantic root of bounded survival.

It answers: **how does Koschei stop damage, preserve trustworthy state, recover deterministically and reach finality without turning emergency behavior into unlimited authority?**

`thal` is not merely retry, rollback or disaster recovery.

### Containment law

Containment reduces the system's ability to produce further harmful effects. It is not a cosmetic status flag.

### Recovery law

Recovery must be evidence-bound and non-escalating. Emergency state does not justify manufacturing root authority.

### Finality law

Final recovery decisions require the configured evidence/quorum conditions. Split-brain or conflicting finality evidence fails closed.

### Epoch law

Containment is terminal for ordinary operation within an epoch. Rebirth creates a new epoch with fresh inactive sigil state. Old authority is not resurrected.

### Whole-universe role

`thal` is how the universe survives without betraying `ka` identity, `vor` authority or `shi` evidence, while coordinating with `nur` to shrink exposed surface during danger.

### Minimal invariant set

1. Containment reduces effect surface.
2. Recovery cannot create new privilege from nothing.
3. Recovery is evidence-bound.
4. Conflicting finality blocks commitment.
5. Containment is terminal within the epoch.
6. Rebirth produces a fresh epoch.
7. Old-epoch authority does not survive rebirth.

---

## 5. `nur`

### Core identity

`nur` is the semantic root of controlled knowability.

It answers: **what may be seen, inferred, correlated or retained about the system without confusing knowledge with authority?**

`nur` is not obfuscation and it is not a promise that software can make all information unknowable. It is a discipline for reducing unnecessary exposure, compartmentalizing knowledge and keeping visibility separate from privilege.

### Visibility law

A component receives only the visibility required for its role. Broader observation does not grant broader authority.

### Compartment law

Aliases, routes, representations and compartments may rotate while canonical identity and required evidence continuity remain intact.

### Knowledge-budget law

Security-sensitive subsystems may constrain how much structural information is exposed through ordinary operation, diagnostics and failure paths. This must not be implemented by falsifying security evidence required for legitimate verification.

### Containment law

During containment, visibility may shrink together with effect surface. Reduced visibility cannot be used to bypass `shi` evidence requirements.

### Whole-universe role

`nur` limits unnecessary knowledge while respecting the truths established by `ka`, the boundaries of `vor`, the evidence requirements of `shi` and the containment/recovery state of `thal`.

### Minimal invariant set

1. Visibility is not authority.
2. Alias knowledge is not canonical identity ownership.
3. Visibility expansion cannot expand capability.
4. Capability expansion cannot bypass visibility policy.
5. Evidence requirements cannot be erased in the name of secrecy.
6. Containment may shrink exposed surface.
7. Representation rotation must preserve required evidence lineage.

---

## Composition law

Sigils are semantic roots, not independent superpowers. Composition must satisfy all participating invariants simultaneously. No combination may weaken another sigil's fail-closed law, manufacture ambient authority, erase required evidence, resurrect old-epoch privilege, or turn visibility into control.

The compact source surface is intentionally smaller than the semantic machinery behind it. The user may write a small Koschei expression; the implementation may activate a much larger verified plan. That hidden machinery is an implementation detail, while the invariants in this lexicon are part of the language's intended meaning.
