---- MODULE BrokerConfinement_TTrace_1795448350 ----
EXTENDS Sequences, TLCExt, Toolbox, Naturals, TLC, BrokerConfinement

_expression ==
    LET BrokerConfinement_TEExpression == INSTANCE BrokerConfinement_TEExpression
    IN BrokerConfinement_TEExpression!expression
----

_trace ==
    LET BrokerConfinement_TETrace == INSTANCE BrokerConfinement_TETrace
    IN BrokerConfinement_TETrace!trace
----

_inv ==
    ~(
        TLCGet("level") = Len(_TETrace)
        /\
        stale = (FALSE)
        /\
        held = (<<1, 0>>)
        /\
        badWrite = (FALSE)
        /\
        scopes = (<<[live |-> TRUE, writable |-> FALSE, tokens |-> 1], [live |-> FALSE, writable |-> FALSE, tokens |-> 0]>>)
        /\
        done = ({"env"})
        /\
        steps = (2)
        /\
        open = (TRUE)
    )
----

_init ==
    /\ done = _TETrace[1].done
    /\ scopes = _TETrace[1].scopes
    /\ held = _TETrace[1].held
    /\ open = _TETrace[1].open
    /\ steps = _TETrace[1].steps
    /\ stale = _TETrace[1].stale
    /\ badWrite = _TETrace[1].badWrite
----

_next ==
    /\ \E i,j \in DOMAIN _TETrace:
        /\ \/ /\ j = i + 1
              /\ i = TLCGet("level")
        /\ done  = _TETrace[i].done
        /\ done' = _TETrace[j].done
        /\ scopes  = _TETrace[i].scopes
        /\ scopes' = _TETrace[j].scopes
        /\ held  = _TETrace[i].held
        /\ held' = _TETrace[j].held
        /\ open  = _TETrace[i].open
        /\ open' = _TETrace[j].open
        /\ steps  = _TETrace[i].steps
        /\ steps' = _TETrace[j].steps
        /\ stale  = _TETrace[i].stale
        /\ stale' = _TETrace[j].stale
        /\ badWrite  = _TETrace[i].badWrite
        /\ badWrite' = _TETrace[j].badWrite

\* Uncomment the ASSUME below to write the states of the error trace
\* to the given file in Json format. Note that you can pass any tuple
\* to `JsonSerialize`. For example, a sub-sequence of _TETrace.
    \* ASSUME
    \*     LET J == INSTANCE Json
    \*         IN J!JsonSerialize("BrokerConfinement_TTrace_1795448350.json", _TETrace)

=============================================================================

 Note that you can extract this module `BrokerConfinement_TEExpression`
  to a dedicated file to reuse `expression` (the module in the 
  dedicated `BrokerConfinement_TEExpression.tla` file takes precedence 
  over the module `BrokerConfinement_TEExpression` below).

---- MODULE BrokerConfinement_TEExpression ----
EXTENDS Sequences, TLCExt, Toolbox, Naturals, TLC, BrokerConfinement

expression == 
    [
        \* To hide variables of the `BrokerConfinement` spec from the error trace,
        \* remove the variables below.  The trace will be written in the order
        \* of the fields of this record.
        done |-> done
        ,scopes |-> scopes
        ,held |-> held
        ,open |-> open
        ,steps |-> steps
        ,stale |-> stale
        ,badWrite |-> badWrite
        
        \* Put additional constant-, state-, and action-level expressions here:
        \* ,_stateNumber |-> _TEPosition
        \* ,_doneUnchanged |-> done = done'
        
        \* Format the `done` variable as Json value.
        \* ,_doneJson |->
        \*     LET J == INSTANCE Json
        \*     IN J!ToJson(done)
        
        \* Lastly, you may build expressions over arbitrary sets of states by
        \* leveraging the _TETrace operator.  For example, this is how to
        \* count the number of times a spec variable changed up to the current
        \* state in the trace.
        \* ,_doneModCount |->
        \*     LET F[s \in DOMAIN _TETrace] ==
        \*         IF s = 1 THEN 0
        \*         ELSE IF _TETrace[s].done # _TETrace[s-1].done
        \*             THEN 1 + F[s-1] ELSE F[s-1]
        \*     IN F[_TEPosition - 1]
    ]

=============================================================================



Parsing and semantic processing can take forever if the trace below is long.
 In this case, it is advised to uncomment the module below to deserialize the
 trace from a generated binary file.

\*
\*---- MODULE BrokerConfinement_TETrace ----
\*EXTENDS IOUtils, TLC, BrokerConfinement
\*
\*trace == IODeserialize("BrokerConfinement_TTrace_1795448350.bin", TRUE)
\*
\*=============================================================================
\*

---- MODULE BrokerConfinement_TETrace ----
EXTENDS TLC, BrokerConfinement

trace == 
    <<
    ([stale |-> FALSE,held |-> <<0, 0>>,badWrite |-> FALSE,scopes |-> <<[live |-> FALSE, writable |-> FALSE, tokens |-> 0], [live |-> FALSE, writable |-> FALSE, tokens |-> 0]>>,done |-> {},steps |-> 0,open |-> TRUE]),
    ([stale |-> FALSE,held |-> <<1, 0>>,badWrite |-> FALSE,scopes |-> <<[live |-> TRUE, writable |-> FALSE, tokens |-> 1], [live |-> FALSE, writable |-> FALSE, tokens |-> 0]>>,done |-> {},steps |-> 1,open |-> TRUE]),
    ([stale |-> FALSE,held |-> <<1, 0>>,badWrite |-> FALSE,scopes |-> <<[live |-> TRUE, writable |-> FALSE, tokens |-> 1], [live |-> FALSE, writable |-> FALSE, tokens |-> 0]>>,done |-> {"env"},steps |-> 2,open |-> TRUE])
    >>
----


=============================================================================

---- CONFIG BrokerConfinement_TTrace_1795448350 ----
CONSTANTS
    Grants = { }
    Compromised = TRUE
    MaxScopes = 2
    MaxSteps = 6
    CheckGrants = FALSE
    CheckWritable = TRUE
    CheckLive = TRUE

INVARIANT
    _inv

CHECK_DEADLOCK
    \* CHECK_DEADLOCK off because of PROPERTY or INVARIANT above.
    FALSE

INIT
    _init

NEXT
    _next

CONSTANT
    _TETrace <- _trace

ALIAS
    _expression
=============================================================================
\* Generated on Mon Nov 23 18:39:11 TRT 2026