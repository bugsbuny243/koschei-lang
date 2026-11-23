---------------------------- MODULE BrokerConfinement ----------------------------
(***************************************************************************)
(* Model of the native broker's request loop (native_broker_v1            *)
(* _ksBrokerLoop): the scope table, reference-counted release, and which  *)
(* requests the broker serves.                                             *)
(*                                                                         *)
(* The worker is either honest (it sends only what the program's compiled *)
(* capability code sends) or compromised (seccomp still holds, but it may *)
(* send any frame on its broker socket). Seccomp itself is trusted: the   *)
(* worker's only route to the host is the broker.                          *)
(*                                                                         *)
(* Grants is what the compiler saw the program use. CheckGrants models    *)
(* the broker refusing requests outside Grants (added after this model    *)
(* found the gap); CheckWritable and CheckLive model the scope checks.    *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS Grants, Compromised, MaxScopes, MaxSteps,
          CheckGrants, CheckWritable, CheckLive

Effects == {"disk_read", "disk_write", "env"}
NoScope == [live |-> FALSE, writable |-> FALSE, tokens |-> 0]

VARIABLES
  scopes,   \* broker table: index -> scope (index 0 is never valid)
  held,     \* honest worker: tokens it holds, per scope index
  done,     \* effects the broker performed
  badWrite, \* a write went through a read-only scope
  stale,    \* a request used a released scope
  open,     \* conversation still open (a malformed request closes it)
  steps
vars == <<scopes, held, done, badWrite, stale, open, steps>>

Idx == 1..MaxScopes

Init ==
  /\ scopes = [i \in Idx |-> NoScope]
  /\ held = [i \in Idx |-> 0]
  /\ done = {} /\ badWrite = FALSE /\ stale = FALSE /\ open = TRUE /\ steps = 0

Granted(e) == ~CheckGrants \/ e \in Grants

\* What the worker may send. An honest worker sends only what its code does.
MaySend(kind, i) ==
  \/ Compromised
  \/ CASE kind = "scope"    -> "disk_read" \in Grants
       [] kind = "scope_rw" -> "disk_write" \in Grants
       [] kind = "env"      -> "env" \in Grants
       [] kind = "release"  -> held[i] > 0
       [] kind = "read"     -> held[i] > 0
       [] kind = "write"    -> held[i] > 0 /\ scopes[i].writable
       [] OTHER             -> FALSE

Close == /\ open' = FALSE /\ UNCHANGED <<scopes, held, done, badWrite, stale>>

\* scope / scope_rw: open (or reuse) a scope. Reuse merges equal scopes;
\* modelled by letting the broker pick any free or same-mode live slot.
Scope(rw) ==
  LET kind == IF rw THEN "scope_rw" ELSE "scope"
      need == IF rw THEN "disk_write" ELSE "disk_read" IN
  /\ MaySend(kind, 1)
  /\ IF ~Granted(need) THEN Close
     ELSE \E i \in Idx :
       /\ \/ ~scopes[i].live
          \/ scopes[i].live /\ scopes[i].writable = rw
       /\ scopes' = [scopes EXCEPT ![i] = [live |-> TRUE, writable |-> rw,
                                           tokens |-> @.tokens + 1]]
       /\ held' = [held EXCEPT ![i] = @ + 1]
       /\ UNCHANGED <<done, badWrite, stale, open>>

Release(i) ==
  /\ MaySend("release", i)
  /\ IF CheckLive /\ ~scopes[i].live THEN Close
     ELSE /\ stale' = (stale \/ ~scopes[i].live)
          /\ scopes' = [scopes EXCEPT ![i] =
                IF @.tokens <= 1 THEN NoScope ELSE [@ EXCEPT !.tokens = @ - 1]]
          /\ held' = [held EXCEPT ![i] = IF @ > 0 THEN @ - 1 ELSE 0]
          /\ UNCHANGED <<done, badWrite, open>>

Use(kind, i) ==
  LET effect == IF kind = "write" THEN "disk_write" ELSE "disk_read" IN
  /\ MaySend(kind, i)
  /\ IF \/ CheckLive /\ ~scopes[i].live
        \/ kind = "write" /\ CheckWritable /\ ~scopes[i].writable
     THEN Close
     ELSE /\ done' = done \cup {effect}
          /\ badWrite' = (badWrite \/ (kind = "write" /\ ~scopes[i].writable))
          /\ stale' = (stale \/ ~scopes[i].live)
          /\ UNCHANGED <<scopes, held, open>>

Env ==
  /\ MaySend("env", 1)
  /\ IF ~Granted("env") THEN Close
     ELSE /\ done' = done \cup {"env"}
          /\ UNCHANGED <<scopes, held, badWrite, stale, open>>

Next ==
  /\ open /\ steps < MaxSteps
  /\ steps' = steps + 1
  /\ \/ Scope(FALSE) \/ Scope(TRUE) \/ Env
     \/ \E i \in Idx : Release(i) \/ Use("read", i) \/ Use("write", i)

Spec == Init /\ [][Next]_vars

\* ---- properties ---------------------------------------------------------
\* 1. The broker performs only effects the compiled program was granted.
Confinement == done \subseteq Grants
\* 2. Nothing is ever written through a read-only scope.
NoWriteThroughReadOnly == ~badWrite
\* 3. A released scope is never used again.
NoStaleScope == ~stale
================================================================================
