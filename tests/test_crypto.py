"""ChaCha20 구현이 RFC 8439와 일치하는지, 봉인이 변조를 잡아내는지 확인한다.

직접 구현한 암호를 테스트 없이 쓰는 것은 위험하다. RFC의 공식 테스트 벡터로
블록 함수와 스트림 암호를 모두 검증한다.
"""

from __future__ import annotations

import pytest

from contract_review_ai.crypto import (
    CryptoError,
    chacha20,
    chacha20_block,
    decrypt,
    encrypt,
    is_encrypted,
)


def test_block_matches_rfc8439_vector():
    """RFC 8439 §2.3.2 테스트 벡터."""
    key = bytes(range(32))
    nonce = bytes.fromhex("000000090000004a00000000")
    block = chacha20_block(key, 1, nonce)

    expected = bytes.fromhex(
        "10f1e7e4d13b5915500fdd1fa32071c4"
        "c7d1f4c733c068030422aa9ac3d46c4e"
        "d2826446079faa0914c2d705d98b02a2"
        "b5129cd1de164eb9cbd083e8a2503c4e"
    )
    assert block == expected


def test_stream_matches_rfc8439_vector():
    """RFC 8439 §2.4.2 — 'Ladies and Gentlemen…' 평문 암호화 벡터."""
    key = bytes(range(32))
    nonce = bytes.fromhex("000000000000004a00000000")
    plaintext = (
        b"Ladies and Gentlemen of the class of '99: If I could offer you "
        b"only one tip for the future, sunscreen would be it."
    )
    expected = bytes.fromhex(
        "6e2e359a2568f98041ba0728dd0d6981"
        "e97e7aec1d4360c20a27afccfd9fae0b"
        "f91b65c5524733ab8f593dabcd62b357"
        "1639d624e65152ab8f530c359f0861d8"
        "07ca0dbf500d6a6156a38e088a22b65e"
        "52bc514d16ccf806818ce91ab7793736"
        "5af90bbf74a35be6b40b8eedf2785e42"
        "874d"
    )
    assert chacha20(key, nonce, plaintext, counter=1) == expected


def test_stream_is_its_own_inverse():
    key = bytes(range(32))
    nonce = bytes(12)
    data = "계약서 본문 · 제7조(손해배상)".encode()
    assert chacha20(key, nonce, chacha20(key, nonce, data)) == data


def test_roundtrip_preserves_bytes():
    data = "제3조(대금 지급)\n갑은 30일 이내에 지급한다.\n".encode()
    sealed = encrypt(data, "열쇠-문구")
    assert is_encrypted(sealed)
    assert data not in sealed  # 평문이 그대로 남아 있으면 안 된다
    assert decrypt(sealed, "열쇠-문구") == data


def test_wrong_passphrase_is_rejected():
    sealed = encrypt(b"secret", "열쇠-문구")
    with pytest.raises(CryptoError):
        decrypt(sealed, "다른-열쇠")


def test_tampering_is_detected():
    """본문 한 바이트만 바꿔도 인증에서 걸려야 한다."""
    sealed = bytearray(encrypt("계약 금액은 3억원으로 한다.".encode(), "열쇠"))
    sealed[-40] ^= 0x01  # 암호문 영역 한 비트
    with pytest.raises(CryptoError):
        decrypt(bytes(sealed), "열쇠")


def test_header_tampering_is_detected():
    """salt·nonce를 바꿔치기하는 시도도 인증 범위에 들어간다."""
    sealed = bytearray(encrypt(b"payload", "열쇠"))
    sealed[10] ^= 0x01  # salt 영역
    with pytest.raises(CryptoError):
        decrypt(bytes(sealed), "열쇠")


def test_rejects_plain_file():
    with pytest.raises(CryptoError):
        decrypt("그냥 텍스트 파일입니다".encode(), "열쇠")


def test_each_encryption_uses_fresh_nonce():
    a = encrypt(b"same", "열쇠")
    b = encrypt(b"same", "열쇠")
    assert a != b
    assert decrypt(a, "열쇠") == decrypt(b, "열쇠") == b"same"
