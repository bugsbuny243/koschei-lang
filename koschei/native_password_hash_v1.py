"""HMAC-SHA256, PBKDF2-HMAC-SHA256 and constant-time equality in native binaries.

Go's standard ``crypto/hmac``, ``crypto/sha256``, ``crypto/pbkdf2`` and
``crypto/subtle`` are the providers; this fragment only checks the
``password_hash_v1`` parameters, in its order and with its messages.
"""

from __future__ import annotations

from . import password_hash_v1 as _hash

BUILTINS = {
    "hmac_sha256": "_ksHmacSha256",
    "pbkdf2_sha256": "_ksPbkdf2Sha256",
    "secure_equal": "_ksSecureEqual",
}
ARITY = {name: len(signature[0]) for name, signature in _hash.SIGNATURES.items()}
PASSWORD_HASH_IMPORTS = ("crypto/hmac", "crypto/pbkdf2", "crypto/sha256", "crypto/subtle", "encoding/hex")


def password_hash_runtime() -> str:
    from .mir_go_native import _go_string

    return _RUNTIME.format(
        min_salt=_hash.MIN_SALT_BYTES,
        max_salt=_hash.MAX_SALT_BYTES,
        min_iterations=_hash.MIN_ITERATIONS,
        max_iterations=_hash.MAX_ITERATIONS,
        min_key=_hash.MIN_KEY_BYTES,
        max_key=_hash.MAX_KEY_BYTES,
        max_password=_hash.MAX_PASSWORD_BYTES,
        salt_message=_go_string(_hash.SALT_MESSAGE),
        iterations_message=_go_string(_hash.ITERATIONS_MESSAGE),
        key_message=_go_string(_hash.KEY_MESSAGE),
        password_message=_go_string(_hash.PASSWORD_MESSAGE),
    )


_RUNTIME = r'''
// ---- HMAC and PBKDF2 (native_password_hash_v1) ----------------------------

func _ksHashBytes(raw any, name string) string {{
	value, ok := raw.(_ksBytes)
	if !ok {{
		_ksAbort("KS5002", name+" Bytes argument drifted")
	}}
	return value.data
}}

func _ksHmacSha256(rawKey any, rawMessage any) any {{
	mac := hmac.New(sha256.New, []byte(_ksHashBytes(rawKey, "hmac_sha256")))
	mac.Write([]byte(_ksHashBytes(rawMessage, "hmac_sha256")))
	return hex.EncodeToString(mac.Sum(nil))
}}

func _ksPbkdf2Sha256(rawPassword any, rawSalt any, rawIterations any, rawLength any) any {{
	password := _ksHashBytes(rawPassword, "pbkdf2_sha256")
	salt := _ksHashBytes(rawSalt, "pbkdf2_sha256")
	iterations, okIterations := rawIterations.(int64)
	length, okLength := rawLength.(int64)
	if !okIterations || !okLength {{
		_ksAbort("KS5002", "pbkdf2_sha256 Int argument drifted")
	}}
	if len(salt) < {min_salt} || len(salt) > {max_salt} {{
		return _ksError{{message: {salt_message}}}
	}}
	if iterations < {min_iterations} || iterations > {max_iterations} {{
		return _ksError{{message: {iterations_message}}}
	}}
	if length < {min_key} || length > {max_key} {{
		return _ksError{{message: {key_message}}}
	}}
	if len(password) > {max_password} {{
		return _ksError{{message: {password_message}}}
	}}
	key, err := pbkdf2.Key(sha256.New, password, []byte(salt), int(iterations), int(length))
	if err != nil {{
		_ksAbort("KS5002", "pbkdf2_sha256 provider refused checked parameters: "+err.Error())
	}}
	return hex.EncodeToString(key)
}}

func _ksSecureEqual(rawLeft any, rawRight any) any {{
	left, okLeft := rawLeft.(string)
	right, okRight := rawRight.(string)
	if !okLeft || !okRight {{
		_ksAbort("KS5002", "secure_equal String argument drifted")
	}}
	return subtle.ConstantTimeCompare([]byte(left), []byte(right)) == 1
}}
'''


__all__ = ["ARITY", "BUILTINS", "PASSWORD_HASH_IMPORTS", "password_hash_runtime"]
