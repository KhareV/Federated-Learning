from nhm.hashing import hash_bytes, hash_canonical_json


def test_canonical_hash_ignores_mapping_insertion_order() -> None:
    first = {"a": 1, "b": 2}
    second = {"b": 2, "a": 1}

    assert hash_canonical_json(first) == hash_canonical_json(second)


def test_different_data_has_different_hash() -> None:
    assert hash_canonical_json({"a": 1}) != hash_canonical_json({"a": 2})


def test_sha256_known_vector() -> None:
    assert hash_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )

