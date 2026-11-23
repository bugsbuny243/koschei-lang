------------------------------ MODULE RegistryLog ------------------------------
(***************************************************************************)
(* Model of how the client reads the registry's public log for one        *)
(* package version (registry_v1.fetch_package + check_log).                *)
(*                                                                         *)
(* The log is a hash chain: every line names the hash of the previous one *)
(* (parse_log). With a collision-resistant hash, "the hash at seq equals   *)
(* the pinned hash" is the same as "the log extends the pinned prefix",   *)
(* so the model compares prefixes directly.                                *)
(*                                                                         *)
(* The attacker serves any log and any index entry. The owner's history is *)
(* what honest clients pinned before; the attacker cannot change what a    *)
(* client already pinned.                                                  *)
(***************************************************************************)
EXTENDS Naturals, Sequences

CONSTANTS MaxLog, CheckPinned, CheckLogMatch, CheckYank

Digests == {"good", "bad"}
Kinds == {"publish", "yank", "unyank"}
Event == [kind : Kinds, digest : Digests]
None == "none"

VARIABLES log, index, lock, pinned, lastNew, lastLogYanked
vars == <<log, index, lock, pinned, lastNew, lastLogYanked>>

IsPrefix(p, s) == Len(p) <= Len(s) /\ SubSeq(s, 1, Len(p)) = p

\* Index of the last event in L whose kind is in K (0 if none).
Last(L, K) == LET is == {i \in 1..Len(L) : L[i].kind \in K}
              IN IF is = {} THEN 0 ELSE CHOOSE i \in is : \A j \in is : j <= i

LatestPublish(L) == Last(L, {"publish"})
LogYanked(L) == LET i == Last(L, {"yank", "unyank"}) IN i > 0 /\ L[i].kind = "yank"

Init ==
  /\ log = <<>> /\ index = [yanked |-> FALSE, digest |-> "good"]
  /\ lock = None /\ pinned = <<>> /\ lastNew = FALSE /\ lastLogYanked = FALSE

\* The registry serves any log up to MaxLog events and any index entry.
Serve ==
  /\ \E n \in 0..MaxLog : \E L \in [1..n -> Event], y \in BOOLEAN, d \in Digests :
       /\ log' = L
       /\ index' = [yanked |-> y, digest |-> d]
  /\ UNCHANGED <<lock, pinned, lastNew, lastLogYanked>>

Sync ==
  /\ CheckPinned => IsPrefix(pinned, log)
  /\ ~(index.yanked /\ index.digest # lock)                      \* fetch_package
  /\ LatestPublish(log) > 0                                       \* check_log: in the log
  /\ CheckLogMatch => log[LatestPublish(log)].digest = index.digest
  /\ CheckYank => index.yanked = LogYanked(log)
  /\ lock' = index.digest
  /\ pinned' = log
  /\ lastNew' = (index.digest # lock)
  /\ lastLogYanked' = LogYanked(log)
  /\ UNCHANGED <<log, index>>

Next == Serve \/ Sync
Spec == Init /\ [][Next]_vars

\* 1. A version the public log says is yanked is never newly installed
\*    (a lock that already holds it may keep it, as with an honest yank).
NoHiddenYank == ~(lastNew /\ lastLogYanked)

\* 2. What a client locks is what the public log says was published last.
LockedIsLogged == lock # None => lock = pinned[LatestPublish(pinned)].digest

\* 3. A client never accepts a log that drops or rewrites what it pinned.
HistoryMonotonic == [][IsPrefix(pinned, pinned')]_vars
================================================================================
