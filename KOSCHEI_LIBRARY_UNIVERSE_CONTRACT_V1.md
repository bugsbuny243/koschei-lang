# Koschei Library + Universe Contract v1

Status: architectural invariant

Koschei Lang is not allowed to collapse into a conventional language with renamed syntax. The visible language, the Koschei Library, and the Koschei Universe are distinct layers with distinct responsibilities.

## The three layers

### 1. Visible Koschei Language

This is the deliberately small surface a developer writes: native sigils such as `ka`, `vor`, `shi`, `thal`, `nur` and future Koschei-native forms.

The visible source does not need to expose the machinery required to enforce its semantics.

### 2. Koschei Library

The Library is the large semantic and security machinery behind the visible language. It owns reusable mechanisms, verified contracts, capability/effect definitions, evidence machinery, containment/recovery machinery, visibility controls, activation planning, lifecycle rules, epoch rules and future subsystem implementations.

The Library is not a wrapper around React, JavaScript, Node, Python, Rust, Go or another ecosystem. Foreign implementations may exist during bootstrap or at explicit boundaries, but they do not define Koschei semantics.

The Library must expose the smallest surface needed by the language while retaining deep internal machinery. A short source expression may therefore expand into many internal obligations.

### 3. Koschei Universe

The Universe is the coordination physics above individual Library mechanisms. It defines how semantic domains compose, activate, transition, contain, recover, rotate visibility and enter new epochs without violating each other's invariants.

The Universe is not branding. It is executable architecture.

## Expansion rule

A visible sigil is resolved through the lexicon, expanded into Library obligations, composed with Universe interaction laws, ordered by the activation engine, checked against lifecycle/epoch state, and only then permitted to reach execution machinery.

Conceptually:

`visible Koschei -> semantic lexicon -> Library expansion -> Universe composition -> activation/lifecycle proof -> execution`

No implementation may shortcut this architecture by mapping a sigil directly to an unrelated foreign-language primitive when that shortcut drops Koschei obligations.

## Library invisibility rule

Developers should not need to understand or manually wire every internal Library subsystem in order to obtain the guarantees represented by a Koschei sigil. Internal complexity is hidden for usability, not hidden from verification.

Security evidence required to prove behavior must remain inspectable through authorized proof interfaces. "Hidden Library" must never mean unverifiable black box.

## Universe conservation rule

No Library subsystem or Universe interaction may:

- create ambient authority;
- turn visibility into authority;
- turn evidence into authority;
- resurrect authority from an older epoch;
- bypass containment because a subsystem is considered internal;
- erase evidence required for finality;
- weaken another active sigil's fail-closed invariant.

## Native evolution rule

New language words must be born from a semantic need, not from a desire to rename an existing keyword. Before a new sigil becomes canonical it needs a deep lexicon entry, Library obligations, composition rules, lifecycle behavior, failure behavior and tests.

## Product-scale rule

Large systems such as marketplaces, exchanges, financial infrastructure, distributed services or security systems should be expressible with a small Koschei surface while the Library and Universe automatically expand the relevant guarantees.

This is the intended asymmetry:

`small visible language / large verified internal machinery`

The size of the hidden machinery is not itself a security property. Its value comes from explicit invariants, deterministic composition, constrained authority, evidence and fail-closed enforcement.
