"""원장이 변조를 실제로 잡아내는지, 저장소가 암호화한 채로도 도는지 확인한다."""

from __future__ import annotations

import json

from contract_review_ai.crypto import is_encrypted
from contract_review_ai.ledger import GENESIS, Ledger
from contract_review_ai.versioning import VersionStore


def _ledger(tmp_path) -> Ledger:
    return Ledger(tmp_path / "ledger.jsonl")


def test_chain_links_each_block_to_the_previous(tmp_path):
    ledger = _ledger(tmp_path)
    first = ledger.append("registered", "계약A", "v1", "a" * 64, label="초안")
    second = ledger.append("registered", "계약A", "v2", "b" * 64, label="상대방 1차")

    assert first.prev == GENESIS
    assert second.prev == first.hash
    assert ledger.tip() == second.hash
    assert ledger.verify().ok


def test_editing_a_block_breaks_verification(tmp_path):
    """해시는 그대로 두고 내용만 고치면 그 지점이 드러나야 한다."""
    ledger = _ledger(tmp_path)
    for index in range(4):
        ledger.append("registered", "계약A", f"v{index + 1}", f"{index}" * 64)

    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    block = json.loads(lines[2])
    block["sha256"] = "f" * 64
    lines[2] = json.dumps(block, ensure_ascii=False)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = ledger.verify()
    assert result.ok is False
    assert result.broken_at == 2


def test_removing_a_block_breaks_the_chain(tmp_path):
    ledger = _ledger(tmp_path)
    for index in range(4):
        ledger.append("registered", "계약A", f"v{index + 1}", f"{index}" * 64)

    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = ledger.verify()
    assert result.ok is False
    assert result.broken_at == 1


def test_store_encrypts_and_reads_back(tmp_path):
    source = tmp_path / "draft.txt"
    source.write_text("제1조(목적)\n본 계약은 시연용이다.\n", encoding="utf-8")

    store = VersionStore(tmp_path / "versions", passphrase="열쇠-문구")
    record = store.add("계약A", source, label="초안")

    stored = store.resolve("계약A", "v1")
    assert stored.suffix == ".enc"
    assert is_encrypted(stored.read_bytes())
    assert "제1조" not in stored.read_text(encoding="utf-8", errors="replace")

    # 해시는 평문 기준이라 암호화 여부와 무관하게 같다.
    assert record.sha256 == __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    assert store.read_bytes("계약A", "v1") == source.read_bytes()

    with store.open_version("계약A", "v1") as path:
        assert "제1조(목적)" in path.read_text(encoding="utf-8")


def test_store_without_key_stays_plain(tmp_path):
    source = tmp_path / "draft.txt"
    source.write_text("평문 보관", encoding="utf-8")

    store = VersionStore(tmp_path / "versions", passphrase="")
    store.add("계약A", source)

    stored = store.resolve("계약A", "v1")
    assert stored.suffix == ".txt"
    assert stored.read_text(encoding="utf-8") == "평문 보관"


def test_registration_appends_to_the_ledger(tmp_path):
    source = tmp_path / "draft.txt"
    source.write_text("내용", encoding="utf-8")

    store = VersionStore(tmp_path / "versions", passphrase="열쇠")
    store.add("계약A", source, label="초안")

    blocks = store.ledger.for_contract("계약A")
    assert [b.version for b in blocks] == ["v1"]
    assert blocks[0].kind == "registered"
    assert store.ledger.verify().ok
