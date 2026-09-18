"""Koschei Lang token-entitlement admission contract v1.

This module owns product admission facts only.  It deliberately performs no
wallet cryptography, Solana RPC, session issuance, compiler capability checks,
or Khar decisions.  Those facts must be supplied by independently verified
boundaries and are reduced here to one deterministic fail-closed decision.

See KOSCHEI_LANG_TOKEN_ENTITLEMENT_V1.md.
"""
from __future__ import annotations

from dataclasses import dataclass


LANG_ENTITLEMENT_CONTRACT = "koschei.lang-token-entitlement/v1"
LANG_ACCESS_MINT = "Crm17unohCsVQcXeoC4RqpYUUgFXsZVXpVjHq3a8pump"
LANG_REQUIRED_WHOLE_TOKENS = 50_000_000
FINALIZED_COMMITMENT = "finalized"


@dataclass(frozen=True, slots=True)
class VerifiedWalletProofV1:
    wallet: str
    challenge_hash: str
    challenge_consumed: bool
    signature_verified: bool


@dataclass(frozen=True, slots=True)
class VerifiedTokenBalanceV1:
    wallet: str
    mint: str
    decimals: int
    raw_balance: int
    commitment: str
    slot: int


@dataclass(frozen=True, slots=True)
class LangEntitlementDecisionV1:
    contract: str
    wallet: str
    mint: str
    required_raw_balance: int
    observed_raw_balance: int
    decimals: int
    commitment: str
    slot: int
    challenge_hash: str
    allowed: bool
    reason: str


def _required_raw_balance(decimals: int) -> int:
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 255:
        raise ValueError("canonical mint decimals must be an integer in 0..255")
    return LANG_REQUIRED_WHOLE_TOKENS * (10 ** decimals)


def decide_lang_entitlement_v1(
    wallet: VerifiedWalletProofV1,
    balance: VerifiedTokenBalanceV1,
) -> LangEntitlementDecisionV1:
    """Reduce already-verified evidence to a product admission decision.

    The caller MUST obtain both inputs from verification boundaries.  This
    function never turns an address, client-reported balance, token metadata,
    or unfinalized chain observation into authority.
    """

    if not wallet.wallet or not balance.wallet:
        raise ValueError("wallet identity is required")
    if wallet.wallet != balance.wallet:
        raise ValueError("wallet proof and token balance owner do not match")
    if balance.mint != LANG_ACCESS_MINT:
        raise ValueError("token balance is not for the canonical Lang access mint")
    if balance.commitment != FINALIZED_COMMITMENT:
        raise ValueError("Lang entitlement requires finalized Solana state")
    if isinstance(balance.slot, bool) or not isinstance(balance.slot, int) or balance.slot < 0:
        raise ValueError("canonical Solana slot must be a non-negative integer")
    if isinstance(balance.raw_balance, bool) or not isinstance(balance.raw_balance, int) or balance.raw_balance < 0:
        raise ValueError("canonical raw token balance must be a non-negative integer")
    if not wallet.challenge_hash:
        raise ValueError("challenge evidence is required")

    required = _required_raw_balance(balance.decimals)
    proof_ok = wallet.signature_verified and wallet.challenge_consumed
    enough = balance.raw_balance >= required
    allowed = proof_ok and enough

    if not wallet.signature_verified:
        reason = "wallet-signature-not-verified"
    elif not wallet.challenge_consumed:
        reason = "challenge-not-consumed"
    elif not enough:
        reason = "balance-below-threshold"
    else:
        reason = "entitlement-satisfied"

    return LangEntitlementDecisionV1(
        contract=LANG_ENTITLEMENT_CONTRACT,
        wallet=wallet.wallet,
        mint=balance.mint,
        required_raw_balance=required,
        observed_raw_balance=balance.raw_balance,
        decimals=balance.decimals,
        commitment=balance.commitment,
        slot=balance.slot,
        challenge_hash=wallet.challenge_hash,
        allowed=allowed,
        reason=reason,
    )
