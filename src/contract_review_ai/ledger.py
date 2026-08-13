"""문서 등록 원장 — 해시로 이어 붙인 블록 체인.

계약 협상에서 다투게 되는 것은 "그때 받은 문서가 정말 이것이었나"다. 버전 저장소가
파일의 sha256을 기록하지만, 기록 자체를 나중에 고치면 그만이다. 그래서 등록·편집이
일어날 때마다 블록을 하나 덧붙이고, 각 블록이 앞 블록의 해시를 품게 한다.

    블록 = { index, at, kind, contract_id, version, sha256, label, note, prev, hash }
    hash = sha256(prev + 정규화한 본문)

중간 블록을 하나라도 고치면 그 뒤 블록의 해시가 전부 어긋나므로, 어느 지점에서
기록이 손댔는지까지 짚어낼 수 있다. 원장은 append-only JSONL로 남는다.

분산 합의는 하지 않는다 — 노드도 채굴도 없다. 한 조직 안에서 '기록을 조용히 고칠 수
없게' 만드는 것이 목적이고, 그 목적에는 해시 체인으로 충분하다. 외부에 증명해야
한다면 주기적으로 최신 블록 해시(체인 팁)를 타임스탬프 기관이나 공개 원장에
고정(anchoring)하면 된다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

GENESIS = "0" * 64
DEFAULT_PATH = Path("data/ledger.jsonl")


@dataclass
class Block:
    index: int
    at: str
    kind: str
    """registered / edited / meeting / imported."""

    contract_id: str
    version: str
    sha256: str
    """문서 평문의 해시 — 암호화 여부와 무관하게 내용이 같으면 같은 값."""

    label: str = ""
    note: str = ""
    actor: str = ""
    prev: str = GENESIS
    hash: str = ""

    def payload(self) -> dict:
        data = asdict(self)
        data.pop("hash", None)
        return data

    def compute_hash(self) -> str:
        body = json.dumps(self.payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class Verification:
    ok: bool
    length: int
    broken_at: int | None = None
    reason: str = ""
    tip: str = GENESIS

    @property
    def label(self) -> str:
        if self.ok:
            return f"무결성 확인 · 블록 {self.length}개"
        return f"블록 {self.broken_at}에서 불일치 — {self.reason}"


class Ledger:
    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path)

    # ---------- 읽기 ----------

    def blocks(self) -> list[Block]:
        if not self.path.is_file():
            return []
        out: list[Block] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Block(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def tip(self) -> str:
        blocks = self.blocks()
        return blocks[-1].hash if blocks else GENESIS

    def for_contract(self, contract_id: str) -> list[Block]:
        return [b for b in self.blocks() if b.contract_id == contract_id]

    # ---------- 쓰기 ----------

    def append(
        self,
        kind: str,
        contract_id: str,
        version: str,
        sha256: str,
        label: str = "",
        note: str = "",
        actor: str = "",
    ) -> Block:
        blocks = self.blocks()
        block = Block(
            index=len(blocks),
            at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            kind=kind,
            contract_id=contract_id,
            version=version,
            sha256=sha256,
            label=label,
            note=note,
            actor=actor,
            prev=blocks[-1].hash if blocks else GENESIS,
        )
        block.hash = block.compute_hash()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(block), ensure_ascii=False) + "\n")
        return block

    # ---------- 검증 ----------

    def verify(self) -> Verification:
        """앞에서부터 훑으며 연결과 해시를 모두 확인한다."""
        blocks = self.blocks()
        previous = GENESIS

        for position, block in enumerate(blocks):
            if block.index != position:
                return Verification(False, len(blocks), position, "블록 번호가 어긋납니다.")
            if block.prev != previous:
                return Verification(False, len(blocks), position, "앞 블록과 연결이 끊겼습니다.")
            if block.hash != block.compute_hash():
                return Verification(False, len(blocks), position, "블록 내용이 변조됐습니다.")
            previous = block.hash

        return Verification(True, len(blocks), tip=previous)


@dataclass
class ChainSummary:
    """계약 하나의 체인 요약 — 화면 표시용."""

    contract_id: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def tip(self) -> str:
        return self.blocks[-1].hash if self.blocks else GENESIS
