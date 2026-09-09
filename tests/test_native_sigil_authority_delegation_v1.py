import unittest
from dataclasses import replace
import hashlib

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

    def _root(self, mir, **overrides):
        fields = dict(
            grant_id="root-1", subject="deploy", actor_identity_digest="operator",
            epoch=7, operations=("code.write", "deploy.execute"),
        )
        fields.update(overrides)
        return issue_root_grant(mir, **fields)

    def test_valid_v1_seal_is_unchanged(self) -> None:
        root = self._root(self._mir())
        self.assertEqual(root.digest, "2d93d24345dd09f3b44cabbab99e64ea29674ade08ec308a133ef35a7a212fd2")

    def test_comma_operation_cannot_alias_two_granted_operations(self) -> None:
        # In the previous v1 encoder these distinct operation sets had the same
        # seal. Reject the ambiguous name rather than changing valid v1 seals.
        mir = self._mir()
        self._root(mir, operations=("code.write", "deploy.execute"))
        with self.assertRaisesRegex(AuthorityDelegationError, "comma delimiter"):
            self._root(mir, operations=("code.write,deploy.execute",))

    def test_operation_collection_cannot_be_a_string_or_contain_non_strings(self) -> None:
        mir = self._mir()
        for operations in ("repo.read", b"repo.read", None, (), ("",), (7,), ("repo.read", None)):
            with self.subTest(operations=operations), self.assertRaises(AuthorityDelegationError):
                self._root(mir, operations=operations)

    def test_identity_fields_reject_control_delimiters_and_non_strings(self) -> None:
        mir = self._mir()
        for field in ("grant_id", "actor_identity_digest", "subject"):
            for value in ("", 7, None, "a\nb", "a\rb", "a\x00b", "a\tb", "a\x7fb"):
                with self.subTest(field=field, value=value), self.assertRaises(AuthorityDelegationError):
                    self._root(mir, **{field: value})

    def test_operation_names_reject_control_characters(self) -> None:
        mir = self._mir()
        for value in ("read\nwrite", "read\rwrite", "read\x00write"):
            with self.subTest(value=value), self.assertRaises(AuthorityDelegationError):
                self._root(mir, operations=(value,))

    def test_epoch_requires_an_actual_nonnegative_integer(self) -> None:
        mir = self._mir()
        self._root(mir, epoch=0)
        for epoch in (-1, True, False, 7.0, "7", None):
            with self.subTest(epoch=epoch), self.assertRaises(AuthorityDelegationError):
                self._root(mir, epoch=epoch)

    def test_unknown_and_boolean_versions_are_rejected(self) -> None:
        mir = self._mir()
        root = self._root(mir)
        for version in (0, 2, True, 1.0, "1", None):
            with self.subTest(version=version), self.assertRaisesRegex(AuthorityDelegationError, "version"):
                replace(root, version=version).assert_sealed(mir)

    def test_rehashed_invalid_parent_metadata_is_rejected(self) -> None:
        mir = self._mir()
        root = self._root(mir)
        for depth, parent in ((0, "a" * 64), (1, "ROOT"), (1, "invalid"), (1, "A" * 64), (-1, "ROOT"), (True, "a" * 64), (1.0, "a" * 64)):
            # Construct self-consistent but structurally invalid v1 wire data.
            values = (root.grant_id, root.subject, root.actor_identity_digest, str(root.epoch),
                      ",".join(root.operations), root.native_mir_fingerprint,
                      root.universe_plan_digest, parent, str(depth))
            digest = hashlib.sha256(b"koschei.native-sigil-authority-delegation/v1\x00" + "\n".join(values).encode()).hexdigest()
            forged = replace(root, depth=depth, parent_grant_digest=parent, digest=digest)
            with self.subTest(depth=depth, parent=parent), self.assertRaises(AuthorityDelegationError):
                forged.assert_sealed(mir)

    def test_delegation_rejects_unsupported_parent_version(self) -> None:
        mir = self._mir()
        parent = replace(self._root(mir), version=2)
        with self.assertRaises(AuthorityDelegationError):
            delegate_grant(mir, parent, grant_id="child", actor_identity_digest="agent", operations=("code.write",))

    def test_request_gate_rejects_unsupported_grant_version(self) -> None:
        mir = self._mir()
        root = self._root(mir)
        request = seal_effect_request(mir, effect_id="effect", subject="deploy", operation="code.write",
                                      request_digest="payload", identity_digest="operator", epoch=7, nonce_digest="nonce")
        with self.assertRaises(AuthorityDelegationError):
            require_request_authority(mir, request, replace(root, version=2))

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
