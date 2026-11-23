---- MODULE PackageUpdate_TTrace_1795444961 ----
EXTENDS Sequences, TLCExt, Toolbox, PackageUpdate, Naturals, TLC

_expression ==
    LET PackageUpdate_TEExpression == INSTANCE PackageUpdate_TEExpression
    IN PackageUpdate_TEExpression!expression
----

_trace ==
    LET PackageUpdate_TETrace == INSTANCE PackageUpdate_TETrace
    IN PackageUpdate_TETrace!trace
----

_inv ==
    ~(
        TLCGet("level") = Len(_TETrace)
        /\
        flagNewSigner = (FALSE)
        /\
        log = (<<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"], [surface |-> {}, honest |-> TRUE, signer |-> "none"]>>)
        /\
        lock = ([surface |-> {}, signer |-> "none", present |-> TRUE, pinned |-> <<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"], [surface |-> {}, honest |-> TRUE, signer |-> "none"]>>])
        /\
        consented = ({})
    )
----

_init ==
    /\ consented = _TETrace[1].consented
    /\ lock = _TETrace[1].lock
    /\ flagNewSigner = _TETrace[1].flagNewSigner
    /\ log = _TETrace[1].log
----

_next ==
    /\ \E i,j \in DOMAIN _TETrace:
        /\ \/ /\ j = i + 1
              /\ i = TLCGet("level")
        /\ consented  = _TETrace[i].consented
        /\ consented' = _TETrace[j].consented
        /\ lock  = _TETrace[i].lock
        /\ lock' = _TETrace[j].lock
        /\ flagNewSigner  = _TETrace[i].flagNewSigner
        /\ flagNewSigner' = _TETrace[j].flagNewSigner
        /\ log  = _TETrace[i].log
        /\ log' = _TETrace[j].log

\* Uncomment the ASSUME below to write the states of the error trace
\* to the given file in Json format. Note that you can pass any tuple
\* to `JsonSerialize`. For example, a sub-sequence of _TETrace.
    \* ASSUME
    \*     LET J == INSTANCE Json
    \*         IN J!JsonSerialize("PackageUpdate_TTrace_1795444961.json", _TETrace)

=============================================================================

 Note that you can extract this module `PackageUpdate_TEExpression`
  to a dedicated file to reuse `expression` (the module in the 
  dedicated `PackageUpdate_TEExpression.tla` file takes precedence 
  over the module `PackageUpdate_TEExpression` below).

---- MODULE PackageUpdate_TEExpression ----
EXTENDS Sequences, TLCExt, Toolbox, PackageUpdate, Naturals, TLC

expression == 
    [
        \* To hide variables of the `PackageUpdate` spec from the error trace,
        \* remove the variables below.  The trace will be written in the order
        \* of the fields of this record.
        consented |-> consented
        ,lock |-> lock
        ,flagNewSigner |-> flagNewSigner
        ,log |-> log
        
        \* Put additional constant-, state-, and action-level expressions here:
        \* ,_stateNumber |-> _TEPosition
        \* ,_consentedUnchanged |-> consented = consented'
        
        \* Format the `consented` variable as Json value.
        \* ,_consentedJson |->
        \*     LET J == INSTANCE Json
        \*     IN J!ToJson(consented)
        
        \* Lastly, you may build expressions over arbitrary sets of states by
        \* leveraging the _TETrace operator.  For example, this is how to
        \* count the number of times a spec variable changed up to the current
        \* state in the trace.
        \* ,_consentedModCount |->
        \*     LET F[s \in DOMAIN _TETrace] ==
        \*         IF s = 1 THEN 0
        \*         ELSE IF _TETrace[s].consented # _TETrace[s-1].consented
        \*             THEN 1 + F[s-1] ELSE F[s-1]
        \*     IN F[_TEPosition - 1]
    ]

=============================================================================



Parsing and semantic processing can take forever if the trace below is long.
 In this case, it is advised to uncomment the module below to deserialize the
 trace from a generated binary file.

\*
\*---- MODULE PackageUpdate_TETrace ----
\*EXTENDS IOUtils, PackageUpdate, TLC
\*
\*trace == IODeserialize("PackageUpdate_TTrace_1795444961.bin", TRUE)
\*
\*=============================================================================
\*

---- MODULE PackageUpdate_TETrace ----
EXTENDS PackageUpdate, TLC

trace == 
    <<
    ([flagNewSigner |-> FALSE,log |-> <<>>,lock |-> [surface |-> {}, signer |-> "none", present |-> FALSE, pinned |-> <<>>],consented |-> {}]),
    ([flagNewSigner |-> FALSE,log |-> <<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"]>>,lock |-> [surface |-> {}, signer |-> "none", present |-> FALSE, pinned |-> <<>>],consented |-> {}]),
    ([flagNewSigner |-> FALSE,log |-> <<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"], [surface |-> {}, honest |-> TRUE, signer |-> "none"]>>,lock |-> [surface |-> {}, signer |-> "none", present |-> FALSE, pinned |-> <<>>],consented |-> {}]),
    ([flagNewSigner |-> FALSE,log |-> <<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"], [surface |-> {}, honest |-> TRUE, signer |-> "none"]>>,lock |-> [surface |-> {}, signer |-> "mallory", present |-> TRUE, pinned |-> <<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"], [surface |-> {}, honest |-> TRUE, signer |-> "none"]>>],consented |-> {}]),
    ([flagNewSigner |-> FALSE,log |-> <<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"], [surface |-> {}, honest |-> TRUE, signer |-> "none"]>>,lock |-> [surface |-> {}, signer |-> "none", present |-> TRUE, pinned |-> <<[surface |-> {}, honest |-> TRUE, signer |-> "mallory"], [surface |-> {}, honest |-> TRUE, signer |-> "none"]>>],consented |-> {}])
    >>
----


=============================================================================

---- CONFIG PackageUpdate_TTrace_1795444961 ----
CONSTANTS
    Caps = { "disk" , "net" }
    Deny = { }
    RequireSigned = FALSE
    MaxLog = 2
    CheckWidening = TRUE
    CheckSigner = FALSE
    CheckLog = TRUE
    CheckSurfaceClaim = TRUE

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
\* Generated on Mon Nov 23 17:42:42 TRT 2026