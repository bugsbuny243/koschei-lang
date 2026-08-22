import unittest

from koschei.native_sigil_authority_delegation_v1 import (
    AuthorityDelegationError,
    delegate_grant,
    issue_root_grant,
    require_request_authority,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_request_binding_v1 import seal_effect_request
from koschei.parser import parse


class AuthorityDelegationTests(unittest.TestCase):
    def _mir(self):
        return lower_native_sigils(parse("ka treasury; vor deploy; shi proof; thal recovery; nur view;"))

    def test_child_grant_can_only_narrow_parent(self) -> None:
        mir = self._mir()
        root = issue_root_grant(
            mir,
            grant_id="root-1",
            subject="deploy",
            actor_identity_digest="operator",
            epoch=7,
            operations=("repo.read", "code.write", "deploy.execute"),
        )
        child = delegate_grant(
            mir,
            root,
            grant_id="agent-1",
            actor_identity_digest="agent",
            operations=("repo.read", "code.write"),
        )
        self.assertEqual(child.depth, 1)
        self.assertEqual(child.parent_grant_digest, root.digest)
        self.assertNotIn("deploy.execute", child.operations)

    def test_child_cannot_widen_parent(self) -> None:
        mir = self._mir()
        root = issue_root_grant(
            mir,
            grant_id="root-1",
            subject="deploy",
            actor_identity_digest="operator",
            epoch=7,
            operations=("repo.read",),
        )
        with self.assertRaises(AuthorityDelegationError):
            delegate_grant(
                mir,
                root,
                grant_id="agent-1",
                actor_identity_digest="agent",
                operations=("repo.read", "deploy.execute"),
            )

    def test_request_requires_exact_actor_epoch_subject_and_operation(self) -> None:
        mir = self._mir()
        grant = issue_root_grant(
            mir,
            grant_id="agent-root",
            subject="deploy",
            actor_identity_digest="agent",
            epoch=7,
            operations=("code.write",),
        )
        request = seal_effect_request(
            mir,
            effect_id="effect-1",
            subject="deploy",
            operation="code.write",
            request_digest="payload-a",
            identity_digest="agent",
            epoch=7,
            nonce_digest="nonce-a",
        )
        require_request_authority(mir, request, grant)

        stale = seal_effect_request(
            mir,
            effect_id="effect-2",
            subject="deploy",
            operation="code.write",
            request_digest="payload-b",
            identity_digest="agent",
            epoch=8,
            nonce_digest="nonce-b",
        )
        with self.assertRaises(AuthorityDelegationError):
            require_request_authority(mir, stale, grant)

    def test_agent_with_code_write_cannot_deploy(self) -> None:
        mir = self._mir()
        grant = issue_root_grant(
            mir,
            grant_id="agent-root",
            subject="deploy",
            actor_identity_digest="agent",
            epoch=7,
            operations=("repo.read", "code.write"),
        )
        request = seal_effect_request(
            mir,
            effect_id="effect-deploy",
            subject="deploy",
            operation="deploy.execute",
            request_digest="payload-deploy",
            identity_digest="agent",
            epoch=7,
            nonce_digest="nonce-deploy",
        )
        with self.assertRaises(AuthorityDelegationError):
            require_request_authority(mir, request, grant)


if __name__ == "__main__":
    unittest.main()
