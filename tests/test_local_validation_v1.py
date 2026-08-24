from dataclasses import replace
import hashlib
import unittest

from koschei.local_validation_v1 import (
    LocalValidationError,
    seal_local_validation_receipt_v1,
    seal_local_validation_step_v1,
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def step(step_id: str = "unit-tests", returncode: int = 0):
    return seal_local_validation_step_v1(
        step_id=step_id,
        command=("python", "-m", "unittest"),
        returncode=returncode,
        stdout_sha256=digest(b"stdout"),
        stderr_sha256=digest(b"stderr"),
    )


class LocalValidationV1Tests(unittest.TestCase):
    def test_full_clean_success_is_release_eligible_but_has_no_authority(self):
        receipt = seal_local_validation_receipt_v1(
            source_commit="a" * 40,
            checkout_clean=True,
            profile="full",
            python_version="Python 3.12.0",
            go_version="go version go1.21 linux/amd64",
            platform="Linux-test",
            steps=(step(), step("adversarial-lab")),
        )
        receipt.assert_sealed()
        self.assertTrue(receipt.passed)
        self.assertTrue(receipt.release_eligible)
        self.assertFalse(receipt.authority)
        receipt.require_for_release("a" * 40)

    def test_core_profile_can_pass_but_never_be_release_eligible(self):
        receipt = seal_local_validation_receipt_v1(
            source_commit="a" * 40,
            checkout_clean=True,
            profile="core",
            python_version="Python 3.12.0",
            go_version="go version go1.21 linux/amd64",
            platform="Linux-test",
            steps=(step(),),
        )
        self.assertTrue(receipt.passed)
        self.assertFalse(receipt.release_eligible)
        with self.assertRaisesRegex(LocalValidationError, "full clean local validation"):
            receipt.require_for_release("a" * 40)

    def test_dirty_checkout_cannot_be_release_eligible(self):
        receipt = seal_local_validation_receipt_v1(
            source_commit="a" * 40,
            checkout_clean=False,
            profile="full",
            python_version="Python 3.12.0",
            go_version="go version go1.21 linux/amd64",
            platform="Linux-test",
            steps=(step(),),
        )
        self.assertTrue(receipt.passed)
        self.assertFalse(receipt.release_eligible)

    def test_failed_step_makes_receipt_fail_closed(self):
        receipt = seal_local_validation_receipt_v1(
            source_commit="a" * 40,
            checkout_clean=True,
            profile="full",
            python_version="Python 3.12.0",
            go_version="go version go1.21 linux/amd64",
            platform="Linux-test",
            steps=(step(returncode=1),),
        )
        self.assertFalse(receipt.passed)
        self.assertFalse(receipt.release_eligible)

    def test_step_or_receipt_tamper_fails_closed(self):
        good_step = step()
        with self.assertRaisesRegex(LocalValidationError, "seal mismatch"):
            replace(good_step, stdout_sha256=digest(b"changed")).assert_sealed()

        receipt = seal_local_validation_receipt_v1(
            source_commit="a" * 40,
            checkout_clean=True,
            profile="full",
            python_version="Python 3.12.0",
            go_version="go version go1.21 linux/amd64",
            platform="Linux-test",
            steps=(good_step,),
        )
        with self.assertRaises(LocalValidationError):
            replace(receipt, source_commit="b" * 40).assert_sealed()

    def test_release_receipt_is_bound_to_exact_source_commit(self):
        receipt = seal_local_validation_receipt_v1(
            source_commit="a" * 40,
            checkout_clean=True,
            profile="full",
            python_version="Python 3.12.0",
            go_version="go version go1.21 linux/amd64",
            platform="Linux-test",
            steps=(step(),),
        )
        with self.assertRaisesRegex(LocalValidationError, "different source commit"):
            receipt.require_for_release("b" * 40)


if __name__ == "__main__":
    unittest.main()
