------------------------------ MODULE PackageUpdate ------------------------------
(***************************************************************************)
(* Model of `ks pkg sync` for one registry dependency (koschei/packages_v1 *)
(* sync + registry_v1.check_log / check_signature).                        *)
(*                                                                         *)
(* The attacker owns the registry: it may publish any record, lie about a  *)
(* record's surface in the index, publish unsigned or with its own key,    *)
(* and rewrite (fork/truncate) the public log. It cannot forge the owner's *)
(* signature: records signed "owner" only appear via OwnerPublish.         *)
(*                                                                         *)
(* The user runs sync with any --allow set and --allow-new-signer flag.    *)
(* Those flags are the user's consent and are recorded.                    *)
(*                                                                         *)
(* The Check* constants switch individual checks of the implementation on *)
(* or off. With all TRUE this is the shipped rule; turning one off must    *)
(* produce a counterexample (tests/test_formal_models_v1.py checks this),  *)
(* which shows each check is load-bearing and the properties have teeth.   *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS Caps, Deny, RequireSigned, MaxLog,
          CheckWidening, CheckSigner, CheckLog, CheckSurfaceClaim

Signers == {"owner", "mallory", "none"}
\* surface: what the compiler computes from the archive.
\* honest:  whether the index's listed surface equals it.
Record == [surface : SUBSET Caps, honest : BOOLEAN, signer : Signers]
NoLock == [present |-> FALSE, surface |-> {}, signer |-> "none", listedHonest |-> TRUE, pinned |-> <<>>]

VARIABLES log, lock, consented, flagNewSigner
vars == <<log, lock, consented, flagNewSigner>>

IsPrefix(p, s) == Len(p) <= Len(s) /\ SubSeq(s, 1, Len(p)) = p

TypeOK ==
  /\ log \in Seq(Record) /\ Len(log) <= MaxLog
  /\ lock.present \in BOOLEAN /\ lock.surface \subseteq Caps
  /\ lock.signer \in Signers /\ lock.pinned \in Seq(Record)
  /\ consented \subseteq Caps /\ flagNewSigner \in BOOLEAN

Init == /\ log = <<>> /\ lock = NoLock /\ consented = {} /\ flagNewSigner = FALSE

\* ---- registry side ------------------------------------------------------
Publish(r) ==
  /\ Len(log) < MaxLog
  /\ log' = Append(log, r)
  /\ UNCHANGED <<lock, consented, flagNewSigner>>

AttackerPublish == \E r \in Record : r.signer # "owner" /\ Publish(r)
OwnerPublish    == \E s \in SUBSET Caps : Publish([surface |-> s, honest |-> TRUE, signer |-> "owner"])

\* Fork the log: keep a prefix, then diverge with an attacker record.
Rewrite ==
  /\ Len(log) > 0
  /\ \E k \in 0..(Len(log) - 1), r \in Record :
       /\ r.signer # "owner"
       /\ r # log[k + 1]
       /\ log' = Append(SubSeq(log, 1, k), r)
  /\ UNCHANGED <<lock, consented, flagNewSigner>>

\* ---- user side ----------------------------------------------------------
\* The index serves record i; check_log requires it to be in the public log.
Accepts(r, allow, newSigner) ==
  /\ CheckSurfaceClaim => r.honest                                   \* listed surface = computed
  /\ r.surface \cap Deny = {}                                        \* [policy] deny
  /\ RequireSigned => r.signer # "none"                              \* [policy] require_signed
  /\ CheckSigner => ((lock.present /\ lock.signer # "none" /\ r.signer # lock.signer) => newSigner)
  /\ CheckLog => (lock.present => IsPrefix(lock.pinned, log))      \* history extends pinned
  /\ CheckWidening => (lock.present => (r.surface \ lock.surface) \subseteq allow)

Sync ==
  \E i \in 1..Len(log), allow \in SUBSET Caps, newSigner \in BOOLEAN :
    LET r == log[i] IN
    /\ Accepts(r, allow, newSigner)
    /\ lock' = [present |-> TRUE, surface |-> r.surface, signer |-> r.signer,
                  listedHonest |-> r.honest, pinned |-> log]
    \* Adding a dependency in koschei.toml is consent to its first surface;
    \* afterwards only --allow grants capabilities.
    /\ consented' = consented \cup allow \cup (IF lock.present THEN {} ELSE r.surface)
    /\ flagNewSigner' = newSigner
    /\ UNCHANGED log

Next == AttackerPublish \/ OwnerPublish \/ Rewrite \/ Sync
Spec == Init /\ [][Next]_vars

\* ---- properties ---------------------------------------------------------
\* 1. A locked package never holds a capability the user did not consent to.
NoSilentWidening == lock.present => lock.surface \subseteq consented

\* 1b. A locked version was listed in the registry index with the surface the
\*     compiler computes, so anyone reading the index saw the truth.
IndexTruthful == lock.listedHonest

\* 2. Denied capabilities never reach the lock.
DenyHolds == lock.surface \cap Deny = {}

\* 3. With require_signed, nothing unsigned is ever locked.
SignedHolds == (RequireSigned /\ lock.present) => lock.signer # "none"

\* 4. Once a signer is pinned, the lock moves to another signer only on a
\*    sync run with --allow-new-signer (this also forbids downgrade to unsigned).
SignerPinned ==
  [][(lock.present /\ lock.signer # "none" /\ lock'.signer # lock.signer) => flagNewSigner']_vars

\* 5. Every accepted log extends the history the project saw before: a forked
\*    or truncated registry history is never accepted.
HistoryMonotonic ==
  [][(lock.present /\ lock' # lock) => IsPrefix(lock.pinned, lock'.pinned)]_vars
==================================================================================
