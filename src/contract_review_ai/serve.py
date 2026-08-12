"""로컬 서버 모드 — 브라우저에서 계약서를 올리고 결과를 내려받는다.

    contract-review serve --port 8000

정적 HTML만으로는 파일을 저장할 수 없어 업로드가 불가능하고, 내보내기도 미리
만들어 둔 파일에 의존한다. 이 서버는 표준 라이브러리만으로 그 두 가지를 채운다.

    GET  /                     워크스페이스 (요청 시 최신 상태로 재생성)
    POST /api/upload           계약서 업로드 → 버전 등록 → 워크스페이스 갱신
    GET  /api/download         md / csv / json / html 즉석 생성해 내려받기
    GET  /api/export           계약대장·버전대장 CSV

외부 패키지도, 인터넷도 쓰지 않는다. 사내망 PC에서 그대로 띄울 수 있다.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import Settings
from .models import RiskLevel
from .report import (
    ContractEntry,
    render_contract_index_csv,
    render_csv,
    render_html,
    render_markdown,
    render_version_index_csv,
    render_workspace,
)
from .review import review_versions
from .versioning import VersionStore, build_timeline

_SAFE = re.compile(r"[^0-9A-Za-z가-힣._\- ]+")


@dataclass
class ServerConfig:
    store: VersionStore
    settings: Settings
    views: list[str]
    min_level: RiskLevel = RiskLevel.INFO
    pairs: str = "adjacent"
    rule_files: list[str] | None = None
    disable_rules: list[str] | None = None


def version_pairs(versions: list[str], mode: str) -> list[tuple[str, str]]:
    if len(versions) < 2:
        return []
    if mode == "latest":
        return [(versions[0], versions[-1])]
    if mode == "all":
        return [(a, b) for i, a in enumerate(versions) for b in versions[i + 1 :]]
    pairs = list(zip(versions, versions[1:], strict=False))
    if len(versions) > 2:
        pairs.append((versions[0], versions[-1]))
    return pairs


def build_entries(config: ServerConfig, contract_ids: list[str] | None = None):
    """저장소 상태를 읽어 워크스페이스에 넣을 계약 목록을 만든다."""
    entries: list[ContractEntry] = []
    for contract_id in contract_ids or config.store.contracts():
        records = config.store.versions(contract_id)
        entry = ContractEntry(
            contract_id=contract_id,
            title=config.store.title(contract_id),
            category=config.store.category(contract_id),
            versions=records,
            timeline=build_timeline(config.store, contract_id) if len(records) > 1 else [],
        )
        for before, after in version_pairs([r.version for r in records], config.pairs):
            try:
                entry.results.append(
                    review_versions(
                        contract_id,
                        before,
                        after,
                        store=config.store,
                        settings=config.settings,
                        views=config.views,
                        min_level=config.min_level,
                        rule_files=config.rule_files,
                        disable_rules=config.disable_rules,
                        progress=None,
                    )
                )
            except (FileNotFoundError, ValueError, RuntimeError):
                continue
        entries.append(entry)
    return entries


def _result_for(config: ServerConfig, contract_id: str, before: str, after: str):
    return review_versions(
        contract_id,
        before,
        after,
        store=config.store,
        settings=config.settings,
        views=config.views,
        min_level=config.min_level,
        rule_files=config.rule_files,
        disable_rules=config.disable_rules,
        progress=None,
    )


def _parse_multipart(body: bytes, boundary: bytes) -> tuple[dict[str, str], list[tuple[str, bytes]]]:
    """multipart/form-data 최소 파서.

    cgi 모듈이 3.13에서 빠졌고 외부 의존성은 쓰지 않기로 했으므로 직접 나눈다.
    파일 하나하나가 계약서 원문이라 바이트를 그대로 보존해야 한다.
    """
    fields: dict[str, str] = {}
    files: list[tuple[str, bytes]] = []

    for part in body.split(b"--" + boundary):
        if not part.strip() or part.strip() == b"--":
            continue
        head, _, payload = part.partition(b"\r\n\r\n")
        if not _:
            continue
        payload = payload.rstrip(b"\r\n")
        headers = head.decode("utf-8", errors="replace")

        name_match = re.search(r'name="([^"]*)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)

        file_match = re.search(r'filename="([^"]*)"', headers)
        if file_match and file_match.group(1):
            files.append((file_match.group(1), payload))
        else:
            fields[name] = _decode(payload)

    return fields, files


def _decode(payload: bytes) -> str:
    """브라우저는 UTF-8을 보내지만, Windows 콘솔 도구(curl 등)는 cp949로 보내기도 한다."""
    for encoding in ("utf-8", "cp949"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


class Handler(BaseHTTPRequestHandler):
    config: ServerConfig
    server_version = "CLAUSA"

    def log_message(self, fmt, *args):  # 요청 로그는 조용히
        return

    # ---------------------------------------------------------------- GET

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path in ("/", "/index.html", "/workspace.html"):
            entries = build_entries(self.config)
            self._send(render_workspace(entries).encode("utf-8"), "text/html; charset=utf-8")
            return

        if parsed.path == "/api/download":
            self._download(query)
            return

        if parsed.path == "/api/export":
            self._export(query)
            return

        self._send(b"not found", "text/plain; charset=utf-8", status=404)

    def _download(self, query: dict[str, list[str]]) -> None:
        contract_id = query.get("contract", [""])[0]
        before = query.get("from", ["first"])[0]
        after = query.get("to", ["latest"])[0]
        fmt = query.get("format", ["csv"])[0].lower()

        try:
            result = _result_for(self.config, contract_id, before, after)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)
            return

        renderers = {
            "csv": (render_csv(result, contract_id), "text/csv; charset=utf-8", "csv"),
            "md": (render_markdown(result), "text/markdown; charset=utf-8", "md"),
            "html": (render_html(result), "text/html; charset=utf-8", "html"),
            "json": (
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                "application/json; charset=utf-8",
                "json",
            ),
        }
        if fmt not in renderers:
            self._json({"ok": False, "error": f"알 수 없는 형식: {fmt}"}, status=400)
            return

        text, content_type, suffix = renderers[fmt]
        name = _safe(f"{contract_id}_{result.before_doc.version}-{result.after_doc.version}")
        self._send(
            text.encode("utf-8"),
            content_type,
            filename=f"{name}.{suffix}",
        )

    def _export(self, query: dict[str, list[str]]) -> None:
        kind = query.get("kind", ["contracts"])[0]
        entries = build_entries(self.config)

        if kind == "versions":
            text = render_version_index_csv(
                [
                    {
                        "contract_id": e.contract_id,
                        "title": e.label,
                        "version": r.version,
                        "label": r.label,
                        "imported_at": r.imported_at,
                        "sha256": r.sha256,
                        "note": r.note,
                        "file": r.file,
                    }
                    for e in entries
                    for r in e.versions
                ]
            )
            filename = "버전대장.csv"
        else:
            text = render_contract_index_csv(
                [
                    {
                        "contract_id": e.contract_id,
                        "title": e.label,
                        "category": e.category,
                        "versions": len(e.versions),
                        "latest": e.latest,
                        "high": e.flagged,
                        "updated_at": e.updated_at,
                    }
                    for e in entries
                ]
            )
            filename = "계약대장.csv"

        self._send(text.encode("utf-8"), "text/csv; charset=utf-8", filename=filename)

    # ---------------------------------------------------------------- POST

    def do_POST(self) -> None:
        if urllib.parse.urlparse(self.path).path != "/api/upload":
            self._json({"ok": False, "error": "not found"}, status=404)
            return

        content_type = self.headers.get("Content-Type", "")
        match = re.search(r"boundary=([^;]+)", content_type)
        if not match:
            self._json({"ok": False, "error": "multipart 요청이 아닙니다."}, status=400)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        fields, files = _parse_multipart(body, match.group(1).strip('"').encode())

        contract_id = (fields.get("contract_id") or "").strip()
        if not contract_id:
            self._json({"ok": False, "error": "계약 ID를 입력하십시오."}, status=400)
            return
        if not files:
            self._json({"ok": False, "error": "첨부할 파일이 없습니다."}, status=400)
            return

        labels = [item.strip() for item in (fields.get("labels") or "").split("|")]
        added, skipped = [], []
        temp_dir = Path(tempfile.mkdtemp(prefix="clausa-upload-"))
        try:
            for index, (filename, payload) in enumerate(files):
                path = temp_dir / _safe(filename)
                path.write_bytes(payload)
                label = labels[index] if index < len(labels) and labels[index] else path.stem
                try:
                    record = self.config.store.add(
                        contract_id,
                        path,
                        label=label,
                        note=fields.get("note", ""),
                        title=fields.get("title", ""),
                        category=fields.get("category", ""),
                    )
                    added.append({"version": record.version, "label": record.label})
                except (FileNotFoundError, ValueError) as exc:
                    skipped.append({"file": filename, "reason": str(exc)})
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self._json({"ok": bool(added), "added": added, "skipped": skipped})

    # ---------------------------------------------------------------- 응답

    def _send(
        self, payload: bytes, content_type: str, status: int = 200, filename: str = ""
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            quoted = urllib.parse.quote(filename)
            self.send_header(
                "Content-Disposition", f"attachment; filename*=UTF-8''{quoted}"
            )
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, data: dict, status: int = 200) -> None:
        self._send(
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status=status,
        )


def _safe(name: str) -> str:
    cleaned = _SAFE.sub("_", Path(name).name).strip()
    return cleaned or "upload"


def serve(config: ServerConfig, host: str = "127.0.0.1", port: int = 8000) -> int:
    handler = type("BoundHandler", (Handler,), {"config": config})
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"CLAUSA 워크스페이스: http://{host}:{port}/")
    print("종료하려면 Ctrl+C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        httpd.server_close()
    return 0
