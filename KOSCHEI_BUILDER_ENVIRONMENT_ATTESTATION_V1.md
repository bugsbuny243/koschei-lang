# KOSCHEI BUILDER ENVIRONMENT ATTESTATION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / ENVIRONMENT IDENTITY WIRED / HARDWARE-CLOUD ATTESTATION NOT YET VERIFIED

## PURPOSE

Logical builder names are insufficient independence evidence. V1 binds each builder to
one authenticated environment identity, environment measurement, workload measurement,
attestation authority id and epoch before that builder may participate in verifier
reproducibility.

Sanctioned slice:

`builder identity`
`-> environment bytes measurement`
`-> workload bytes measurement`
`-> BuilderEnvironmentAttestationV1`
`-> VerifierBuilderObservationV1`
`-> two distinct attested environments`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierReproducibleRuntimeAdmissionV1`

## INDEPENDENCE RULE

Builder A and Builder B must differ in both:

- `environment_id`, and
- measured `environment_digest`.

Changing only the logical builder name is insufficient. Reusing the same measured
environment under two ids is rejected.

## ATTESTATION FIELDS

`BuilderEnvironmentAttestationV1` binds:

- builder id,
- environment id,
- environment measurement digest,
- workload measurement digest,
- attestation authority id,
- epoch,
- authority=false.

The bootstrap prototype authenticates this record with a dedicated HMAC key.

## PROTECTS AGAINST

- counting one measured environment twice as independent builders,
- relabeling environment/workload measurements without the attestation key,
- attaching a builder observation to another environment attestation,
- losing builder-environment identity before reproducibility admission.

## DOES NOT PROTECT AGAINST

- a compromised attestation authority,
- two different environment ids controlled by the same attacker,
- cloned/forged environment bytes accepted by a weak attestation source,
- shared hypervisor/host compromise,
- hardware/firmware compromise,
- false claims that bootstrap HMAC attestation is equivalent to TPM/TEE/cloud remote attestation.

## ASSUMPTIONS

- production environment ids map to genuinely isolated execution environments,
- environment/workload measurement inputs are canonical,
- attestation authority keys are separately protected,
- epoch source is trusted,
- builder observations cannot bypass environment-attested issuance.

## FAILURE MODE

This V1 proves that Koschei authenticated two distinct declared/measured environments.
It does not prove hardware-backed isolation. If one authority can mint arbitrary
measurements for two attacker-controlled environments, the independence claim is false.

## NEXT

1. Add provider-neutral hardware/cloud attestation evidence interface.
2. Bind environment attestations to trusted epoch/revocation policy.
3. Require distinct attestation roots or independent administrative domains where policy demands it.
4. Bind builder keys to attested workload identity rather than only HMAC metadata.
5. Close runtime measure-A/execute-B TOCTOU.
