"""계약서 버전 저장소.

계약 하나를 `contract_id` 폴더로 잡고, 등록할 때마다 원본 파일을 그대로 복사해
v1, v2, v3… 로 고정한다. 나중에 "그때 그 문서가 정말 이거였나"를 sha256으로
확인할 수 있어야 실무에서 협상 기록으로 쓸 수 있다.

    data/versions/<contract_id>/
        manifest.json
        v1__초안.txt          (열쇠가 설정되면 v1__초안.txt.enc)
        v2__상대방_수정본.txt

`CONTRACT_REVIEW_KEY`가 설정돼 있으면 원본을 암호화해 저장한다. 해시는 평문 기준으로
기록하므로, 암호화 여부와 무관하게 같은 문서는 같은 sha256을 갖는다. 등록될 때마다
원장(`ledger.py`)에 블록이 하나 붙어 기록을 나중에 조용히 고칠 수 없게 한다.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from ..crypto import CryptoError, derive_key, is_encrypted, seal, unseal
from ..ledger import Ledger
from ..models import VersionRecord

DEFAULT_ROOT = Path("data/versions")
ENC_SUFFIX = ".enc"
SALT_FILE = ".vault"

_PLAIN_CACHE: dict[tuple, bytes] = {}
"""복호화 결과 캐시 — 파일이 바뀌면 mtime·크기가 달라져 자연히 무효화된다."""
KEY_ENV = "CONTRACT_REVIEW_KEY"
_SAFE_RE = re.compile(r"[^0-9A-Za-z가-힣._-]+")


class VersionStore:
    def __init__(
        self,
        root: str | Path = DEFAULT_ROOT,
        passphrase: str | None = None,
        ledger: Ledger | None = None,
    ) -> None:
        self.root = Path(root)
        # 열쇠는 환경변수에서 읽는다. 없으면 평문으로 저장하고, 화면에도 그렇게 표시한다.
        self.passphrase = passphrase if passphrase is not None else os.environ.get(KEY_ENV, "")
        self.ledger = ledger or Ledger(self.root.parent / "ledger.jsonl")
        self._key: bytes | None = None

    @property
    def encrypted(self) -> bool:
        return bool(self.passphrase)

    @property
    def key(self) -> bytes:
        """저장소 키. 파일마다 다시 유도하면 PBKDF2 비용에 응답이 무너지므로,
        salt를 저장소 단위로 고정해 실행당 한 번만 계산한다."""
        if self._key is None:
            self.root.mkdir(parents=True, exist_ok=True)
            salt_path = self.root / SALT_FILE
            if not salt_path.is_file():
                salt_path.write_bytes(os.urandom(16))
            self._key = derive_key(self.passphrase, salt_path.read_bytes())
        return self._key

    @property
    def salt(self) -> bytes:
        self.key  # salt 파일 생성 보장
        return (self.root / SALT_FILE).read_bytes()

    # ---------- 원본 읽기 ----------

    def read_bytes(self, contract_id: str, spec: str) -> bytes:
        """등록된 버전의 평문 바이트. 암호화돼 있으면 풀어서 준다.

        같은 파일을 한 요청에서 여러 번 읽는다(조문 원문·기한·비교본). 파일이
        해시로 고정돼 있으므로 (경로, 수정시각, 크기)가 같으면 내용도 같다.
        """
        path = self.resolve(contract_id, spec)
        blob = path.read_bytes()
        if not is_encrypted(blob):
            return blob
        if not self.passphrase:
            raise CryptoError(
                f"{KEY_ENV}가 설정되지 않아 암호화된 파일을 열 수 없습니다."
            )

        stat = path.stat()
        cache_key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = _PLAIN_CACHE.get(cache_key)
        if cached is not None:
            return cached

        data = unseal(blob, self.key)
        if len(_PLAIN_CACHE) > 512:
            _PLAIN_CACHE.clear()
        _PLAIN_CACHE[cache_key] = data
        return data

    @contextlib.contextmanager
    def open_version(self, contract_id: str, spec: str):
        """파서에 넘길 실제 경로를 내준다.

        평문이면 저장된 파일을 그대로, 암호화돼 있으면 임시 파일로 잠깐 풀어 준다.
        임시 파일은 블록을 벗어나는 즉시 지운다.
        """
        path = self.resolve(contract_id, spec)
        blob = path.read_bytes()
        if not is_encrypted(blob):
            yield path
            return

        data = self.read_bytes(contract_id, spec)
        suffix = "".join(Path(path.stem).suffixes) or Path(path.stem).suffix
        handle = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix or ".txt", prefix="clausa-"
        )
        try:
            handle.write(data)
            handle.close()
            yield Path(handle.name)
        finally:
            Path(handle.name).unlink(missing_ok=True)

    # ---------- 조회 ----------

    def contracts(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "manifest.json").is_file())

    def manifest_path(self, contract_id: str) -> Path:
        return self.root / _safe(contract_id) / "manifest.json"

    def load(self, contract_id: str) -> dict:
        path = self.manifest_path(contract_id)
        if not path.is_file():
            return {"contract_id": contract_id, "title": contract_id, "versions": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def versions(self, contract_id: str) -> list[VersionRecord]:
        records = [VersionRecord(**v) for v in self.load(contract_id).get("versions", [])]
        records.sort(key=lambda r: r.order)
        return records

    def resolve(self, contract_id: str, spec: str) -> Path:
        """"v2", "2", "latest", "first" 를 실제 파일 경로로 바꾼다."""
        records = self.versions(contract_id)
        if not records:
            raise FileNotFoundError(f"등록된 버전이 없습니다: {contract_id}")

        key = spec.strip().lower()
        if key in {"latest", "last", "head"}:
            record = records[-1]
        elif key in {"first", "base"}:
            record = records[0]
        else:
            wanted = key if key.startswith("v") else f"v{key}"
            match = next((r for r in records if r.version.lower() == wanted), None)
            if match is None:
                available = ", ".join(r.version for r in records)
                raise FileNotFoundError(
                    f"{contract_id}에 {spec} 버전이 없습니다. 사용 가능: {available}"
                )
            record = match

        folder = self.root / _safe(contract_id)
        path = folder / record.file
        if path.is_file():
            return path
        sealed = folder / (record.file + ENC_SUFFIX)
        if sealed.is_file():
            return sealed
        return path

    # ---------- 등록 ----------

    def category(self, contract_id: str) -> str:
        return self.load(contract_id).get("category", "") or "미분류"

    def title(self, contract_id: str) -> str:
        return self.load(contract_id).get("title", "") or contract_id

    def status(self, contract_id: str) -> str:
        """수동으로 지정한 진행 상태. 비어 있으면 버전 이력에서 추론한다."""
        return self.load(contract_id).get("status", "")

    def set_status(self, contract_id: str, status: str) -> None:
        manifest = self.load(contract_id)
        manifest["contract_id"] = contract_id
        manifest["status"] = status.strip()
        manifest.setdefault("versions", [])
        path = self.manifest_path(contract_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def parties(self, contract_id: str) -> list[str]:
        """계약 등록 시 지정한 당사자 표기.

        `약칭[=상호][:역할]` 형식이며, 앞에 `-`를 붙이면 자동 인식된 당사자를 제외한다.
        조문에서 당사자를 자동으로 뽑기는 하지만, 정의 문언이 없는 각서나 예시 문구를
        잘못 잡는 계약이 있어 등록 단계에서 한 번 확정해 둔다.
        """
        return [str(item) for item in self.load(contract_id).get("parties", []) if str(item).strip()]

    def set_parties(self, contract_id: str, specs: list[str]) -> None:
        manifest = self.load(contract_id)
        manifest["contract_id"] = contract_id
        manifest["parties"] = [s.strip() for s in specs if s.strip()]
        manifest.setdefault("versions", [])
        path = self.manifest_path(contract_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def split_party_specs(specs: list[str]) -> tuple[list[str], list[str]]:
        """(추가·보정할 당사자, 제외할 당사자)로 나눈다."""
        add, remove = [], []
        for spec in specs:
            spec = spec.strip()
            if not spec:
                continue
            if spec.startswith("-"):
                remove.append(spec[1:].strip())
            else:
                add.append(spec)
        return add, remove

    def add(
        self,
        contract_id: str,
        source: str | Path,
        label: str = "",
        note: str = "",
        title: str = "",
        category: str = "",
    ) -> VersionRecord:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"등록할 파일이 없습니다: {source}")

        folder = self.root / _safe(contract_id)
        folder.mkdir(parents=True, exist_ok=True)
        manifest = self.load(contract_id)
        manifest["contract_id"] = contract_id
        manifest["title"] = title or manifest.get("title") or contract_id
        manifest["category"] = category or manifest.get("category") or ""
        manifest.setdefault("parties", [])
        manifest.setdefault("status", "")

        records = [VersionRecord(**v) for v in manifest.get("versions", [])]
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()

        duplicate = next((r for r in records if r.sha256 == digest), None)
        if duplicate:
            raise ValueError(
                f"내용이 같은 파일이 이미 {duplicate.version}({duplicate.label})으로 등록돼 있습니다."
            )

        version = f"v{max((r.order for r in records), default=0) + 1}"
        label = label or source.stem
        filename = f"{version}__{_safe(label)}{source.suffix}"
        target = folder / filename
        if self.passphrase:
            # 평문 파일은 남기지 않는다.
            target = folder / (filename + ENC_SUFFIX)
            target.write_bytes(seal(data, self.key, self.salt))
        else:
            target.write_bytes(data)

        record = VersionRecord(
            version=version,
            label=label,
            file=filename,
            sha256=digest,
            imported_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            note=note,
        )
        manifest["versions"] = [vars(r) for r in records] + [vars(record)]
        self.manifest_path(contract_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.ledger.append(
            kind="registered",
            contract_id=contract_id,
            version=version,
            sha256=digest,
            label=label,
            note=note,
        )
        return record


def _safe(name: str) -> str:
    cleaned = _SAFE_RE.sub("_", name.strip()).strip("._")
    return cleaned or "contract"


