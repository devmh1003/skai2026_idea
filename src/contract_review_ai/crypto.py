"""저장된 계약서를 암호화한다.

계약서 원문이 그대로 디스크에 놓이면, 저장소 폴더만 복사해도 협상 전략이 통째로
새어 나간다. 등록되는 파일은 암호화해 두고 읽을 때만 복호화한다.

ChaCha20(RFC 8439)으로 암호화하고 HMAC-SHA256으로 인증한다(encrypt-then-MAC).
표준 라이브러리만 쓰기로 한 프로젝트라 ChaCha20은 직접 구현했고, RFC의 공식
테스트 벡터로 검증한다(`tests/test_crypto.py`).

    파일 형식:  MAGIC(8) | 버전(1) | salt(16) | nonce(12) | 암호문 | HMAC(32)

한계를 분명히 해 둔다.
* 검증된 암호 라이브러리(`cryptography`)의 대체물이 아니다. 규제 대상 데이터를
  다룬다면 그쪽을 쓰는 편이 옳다.
* 열쇠는 환경변수에 있다. 실행 중인 프로세스나 열쇠를 가진 사람으로부터
  보호해 주지는 않는다. 막아 주는 것은 '저장소 폴더가 통째로 유출되는 경우'다.
* 열쇠를 잃으면 복호화할 방법이 없다.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import os
import struct

MAGIC = b"CLAUSA01"
VERSION = 1
SALT_SIZE = 16
NONCE_SIZE = 12
MAC_SIZE = 32
PBKDF2_ROUNDS = 200_000

_CONSTANTS = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)  # "expand 32-byte k"
_MASK = 0xFFFFFFFF


class CryptoError(Exception):
    """복호화 실패 — 열쇠가 다르거나 파일이 변조됐다."""


def _rotl(value: int, count: int) -> int:
    value &= _MASK
    return ((value << count) | (value >> (32 - count))) & _MASK


def _quarter_round(state: list[int], a: int, b: int, c: int, d: int) -> None:
    state[a] = (state[a] + state[b]) & _MASK
    state[d] = _rotl(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & _MASK
    state[b] = _rotl(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b]) & _MASK
    state[d] = _rotl(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & _MASK
    state[b] = _rotl(state[b] ^ state[c], 7)


def chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    """RFC 8439 §2.3 — 64바이트 키스트림 블록 하나."""
    if len(key) != 32:
        raise ValueError("키는 32바이트여야 합니다.")
    if len(nonce) != NONCE_SIZE:
        raise ValueError("nonce는 12바이트여야 합니다.")

    state = [
        *_CONSTANTS,
        *struct.unpack("<8I", key),
        counter & _MASK,
        *struct.unpack("<3I", nonce),
    ]
    working = list(state)
    for _ in range(10):  # 20 라운드 = 더블 라운드 10회
        _quarter_round(working, 0, 4, 8, 12)
        _quarter_round(working, 1, 5, 9, 13)
        _quarter_round(working, 2, 6, 10, 14)
        _quarter_round(working, 3, 7, 11, 15)
        _quarter_round(working, 0, 5, 10, 15)
        _quarter_round(working, 1, 6, 11, 12)
        _quarter_round(working, 2, 7, 8, 13)
        _quarter_round(working, 3, 4, 9, 14)

    return struct.pack("<16I", *[(w + s) & _MASK for w, s in zip(working, state, strict=True)])


def chacha20(key: bytes, nonce: bytes, data: bytes, counter: int = 1) -> bytes:
    """RFC 8439 §2.4 — 스트림 암호. 암호화와 복호화가 같은 연산이다.

    바이트를 하나씩 XOR하면 계약서 한 편에 수천 번의 파이썬 루프가 돈다.
    블록 단위로 정수 XOR을 한 번에 처리한다.
    """
    parts = []
    for offset in range(0, len(data), 64):
        chunk = data[offset : offset + 64]
        stream = chacha20_block(key, counter + offset // 64, nonce)[: len(chunk)]
        mixed = int.from_bytes(chunk, "big") ^ int.from_bytes(stream, "big")
        parts.append(mixed.to_bytes(len(chunk), "big"))
    return b"".join(parts)


@functools.lru_cache(maxsize=64)
def derive_key(passphrase: str, salt: bytes) -> bytes:
    """열쇠 문구 → 32바이트 키.

    PBKDF2 20만 회는 한 번은 감수할 값이지만 파일마다 반복하면 응답이 무너진다.
    같은 (문구, salt)는 같은 키이므로 캐시한다. 저장소는 salt를 하나로 고정해
    실행당 한 번만 계산하게 한다(`VersionStore.key`).
    """
    if not passphrase:
        raise ValueError("열쇠 문구가 비어 있습니다.")
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, PBKDF2_ROUNDS, 32)


def seal(data: bytes, key: bytes, salt: bytes) -> bytes:
    """이미 유도된 키로 봉인한다. salt는 복호화 측이 같은 키를 얻도록 함께 넣는다."""
    nonce = os.urandom(NONCE_SIZE)
    header = MAGIC + bytes([VERSION]) + salt + nonce
    ciphertext = chacha20(key, nonce, data)
    mac = hmac.new(_mac_key(key), header + ciphertext, hashlib.sha256).digest()
    return header + ciphertext + mac


def unseal(blob: bytes, key: bytes) -> bytes:
    """이미 유도된 키로 연다."""
    return _open(blob, key)


def salt_of(blob: bytes) -> bytes:
    """봉인된 파일에 박힌 salt."""
    start = len(MAGIC) + 1
    return blob[start : start + SALT_SIZE]


def encrypt(data: bytes, passphrase: str) -> bytes:
    """평문 → 봉인된 바이트."""
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = derive_key(passphrase, salt)

    header = MAGIC + bytes([VERSION]) + salt + nonce
    ciphertext = chacha20(key, nonce, data)
    # 인증은 헤더까지 포함한다 — salt나 nonce를 바꿔치기하는 시도도 막는다.
    mac = hmac.new(_mac_key(key), header + ciphertext, hashlib.sha256).digest()
    return header + ciphertext + mac


def decrypt(blob: bytes, passphrase: str) -> bytes:
    """봉인된 바이트 → 평문. 변조됐으면 CryptoError."""
    if len(blob) < len(MAGIC) + 1 + SALT_SIZE or not blob.startswith(MAGIC):
        raise CryptoError("암호화된 파일 형식이 아닙니다.")
    return _open(blob, derive_key(passphrase, salt_of(blob)))


def _open(blob: bytes, key: bytes) -> bytes:
    head_len = len(MAGIC) + 1 + SALT_SIZE + NONCE_SIZE
    if len(blob) < head_len + MAC_SIZE or not blob.startswith(MAGIC):
        raise CryptoError("암호화된 파일 형식이 아닙니다.")

    version = blob[len(MAGIC)]
    if version != VERSION:
        raise CryptoError(f"지원하지 않는 형식 버전입니다: {version}")

    nonce = blob[len(MAGIC) + 1 + SALT_SIZE : head_len]
    ciphertext = blob[head_len : len(blob) - MAC_SIZE]
    mac = blob[len(blob) - MAC_SIZE :]

    expected = hmac.new(_mac_key(key), blob[: len(blob) - MAC_SIZE], hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise CryptoError("복호화에 실패했습니다. 열쇠가 다르거나 파일이 변조됐습니다.")

    return chacha20(key, nonce, ciphertext)


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


def _mac_key(key: bytes) -> bytes:
    """암호화 키와 인증 키를 분리한다."""
    return hashlib.sha256(b"clausa-mac" + key).digest()
