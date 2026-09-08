from __future__ import annotations

from src.core.api_keys import generate_api_key, hash_api_key


def test_generated_key_has_expected_prefix_format():
    full_key, prefix = generate_api_key()
    assert full_key.startswith("pk_live_")
    assert prefix == full_key[: len(prefix)]
    assert full_key.startswith(prefix)


def test_generated_keys_are_unique():
    key1, _ = generate_api_key()
    key2, _ = generate_api_key()
    assert key1 != key2


def test_hash_is_deterministic():
    key, _ = generate_api_key()
    assert hash_api_key(key) == hash_api_key(key)


def test_different_keys_hash_differently():
    key1, _ = generate_api_key()
    key2, _ = generate_api_key()
    assert hash_api_key(key1) != hash_api_key(key2)


def test_hash_does_not_leak_the_raw_key():
    key, _ = generate_api_key()
    assert key not in hash_api_key(key)
