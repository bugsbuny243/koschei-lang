from __future__ import annotations

import unittest

from koschei.universe_power_domains_v1 import (
    CrossDomainPermit,
    PowerDomain,
    PowerGrant,
    UniversePowerGate,
)


class UniversePowerDomainsV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = UniversePowerGate()
        self.grant = PowerGrant(
            subject="bridge-delegate",
            domain=PowerDomain.AUTHORITY,
            scope="sand/base",
            epoch=7,
            actions=frozenset({"mint"}),
            grant_id="grant-7-authority",
        )

    def test_all_30_implicit_cross_domain_edges_are_absent(self) -> None:
        denied = 0
        for source in PowerDomain:
            grant = PowerGrant(
                subject="subject",
                domain=source,
                scope="resource",
                epoch=3,
                actions=frozenset({"operate"}),
                grant_id=f"grant-{source.value}",
            )
            for target in PowerDomain:
                if target is source:
                    continue
                decision = self.gate.authorize(
                    grant=grant,
                    target_domain=target,
                    action="operate",
                    scope="resource",
                    epoch=3,
                )
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "cross-domain-edge-absent")
                denied += 1
        self.assertEqual(denied, 30)

    def test_sandbox_class_delegate_compromise_cannot_become_mint_reality(self) -> None:
        # Model the critical security fact, not a chain-specific exploit recipe:
        # possession of delegate/authority power alone must not synthesize the
        # separate data/reality power required to create backed asset supply.
        decision = self.gate.authorize(
            grant=self.grant,
            target_domain=PowerDomain.DATA,
            action="mint",
            scope="sand/base",
            epoch=7,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "cross-domain-edge-absent")

    def test_cross_domain_mint_requires_exact_single_edge(self) -> None:
        permit = CrossDomainPermit(
            subject="bridge-delegate",
            source_domain=PowerDomain.AUTHORITY,
            target_domain=PowerDomain.DATA,
            source_grant_id="grant-7-authority",
            action="mint",
            scope="sand/base",
            epoch=7,
            evidence_digest=self.gate.evidence_digest(
                "canonical-lock:ethereum",
                "amount:100",
                "destination:base",
                "epoch:7",
            ),
        )
        decision = self.gate.authorize(
            grant=self.grant,
            target_domain=PowerDomain.DATA,
            action="mint",
            scope="sand/base",
            epoch=7,
            permit=permit,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "explicit-cross-domain-permit")

    def test_old_epoch_permit_dies(self) -> None:
        permit = CrossDomainPermit(
            subject="bridge-delegate",
            source_domain=PowerDomain.AUTHORITY,
            target_domain=PowerDomain.DATA,
            source_grant_id="grant-7-authority",
            action="mint",
            scope="sand/base",
            epoch=6,
            evidence_digest=self.gate.evidence_digest("epoch:6", "locked:100"),
        )
        decision = self.gate.authorize(
            grant=self.grant,
            target_domain=PowerDomain.DATA,
            action="mint",
            scope="sand/base",
            epoch=7,
            permit=permit,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "permit-epoch-mismatch")

    def test_scope_laundering_is_denied(self) -> None:
        permit = CrossDomainPermit(
            subject="bridge-delegate",
            source_domain=PowerDomain.AUTHORITY,
            target_domain=PowerDomain.DATA,
            source_grant_id="grant-7-authority",
            action="mint",
            scope="sand/bnb",
            epoch=7,
            evidence_digest=self.gate.evidence_digest("locked:100", "destination:bnb"),
        )
        decision = self.gate.authorize(
            grant=self.grant,
            target_domain=PowerDomain.DATA,
            action="mint",
            scope="sand/base",
            epoch=7,
            permit=permit,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "permit-scope-mismatch")

    def test_same_domain_grant_still_requires_exact_action_scope_and_epoch(self) -> None:
        self.assertTrue(
            self.gate.authorize(
                grant=self.grant,
                target_domain=PowerDomain.AUTHORITY,
                action="mint",
                scope="sand/base",
                epoch=7,
            ).allowed
        )
        self.assertFalse(
            self.gate.authorize(
                grant=self.grant,
                target_domain=PowerDomain.AUTHORITY,
                action="upgrade",
                scope="sand/base",
                epoch=7,
            ).allowed
        )


if __name__ == "__main__":
    unittest.main()
