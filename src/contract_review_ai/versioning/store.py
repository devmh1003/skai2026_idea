"""계약서 버전 저장소.

계약 하나를 `contract_id` 폴더로 잡고, 등록할 때마다 원본 파일을 그대로 복사해
v1, v2, v3… 로 고정한다. 나중에 "그때 그 문서가 정말 이거였나"를 sha256으로
확인할 수 있어야 실무에서 협상 기록으로 쓸 수 있다.

    data/versions/<contract_id>/
        manifest.json
        v1__초안.txt
        v2__상대방_수정본.txt
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from ..models import VersionRecord

DEFAULT_ROOT = Path("data/versions")
_SAFE_RE = re.compile(r"[^0-9A-Za-z가-힣._-]+")


class VersionStore:
    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)

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

        return self.root / _safe(contract_id) / record.file

    # ---------- 등록 ----------

    def add(
        self,
        contract_id: str,
        source: str | Path,
        label: str = "",
        note: str = "",
        title: str = "",
    ) -> VersionRecord:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"등록할 파일이 없습니다: {source}")

        folder = self.root / _safe(contract_id)
        folder.mkdir(parents=True, exist_ok=True)
        manifest = self.load(contract_id)
        manifest["contract_id"] = contract_id
        manifest["title"] = title or manifest.get("title") or contract_id

        records = [VersionRecord(**v) for v in manifest.get("versions", [])]
        digest = _sha256(source)

        duplicate = next((r for r in records if r.sha256 == digest), None)
        if duplicate:
            raise ValueError(
                f"내용이 같은 파일이 이미 {duplicate.version}({duplicate.label})으로 등록돼 있습니다."
            )

        version = f"v{max((r.order for r in records), default=0) + 1}"
        label = label or source.stem
        filename = f"{version}__{_safe(label)}{source.suffix}"
        shutil.copy2(source, folder / filename)

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
        return record


def _safe(name: str) -> str:
    cleaned = _SAFE_RE.sub("_", name.strip()).strip("._")
    return cleaned or "contract"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
