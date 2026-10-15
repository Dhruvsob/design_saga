import bcrypt

from routes.auth import hash_password, verify_password


def test_password_hash_round_trip_and_rejection():
    hashed = hash_password("correct horse battery staple")

    assert hashed.startswith("$2")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_existing_bcrypt_hashes_remain_compatible():
    legacy = bcrypt.hashpw(b"legacy-password", bcrypt.gensalt()).decode("ascii")

    assert verify_password("legacy-password", legacy)
    assert not verify_password("legacy-password", "not-a-bcrypt-hash")
