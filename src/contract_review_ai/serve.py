"""로컬 서버 모드 — 브라우저에서 계약서를 올리고 결과를 내려받는다.

    contract-review serve --port 8000

정적 HTML만으로는 파일을 저장할 수 없어 업로드가 불가능하고, 내보내기도 미리
만들어 둔 파일에 의존한다. 이 서버는 표준 라이브러리만으로 그 두 가지를 채운다.

    GET  /                     워크스페이스 (요청 시 최신 상태로 재생성)
    POST /api/upload           계약서 업로드 → 버전 등록 → 워크스페이스 갱신
    POST /api/edit             조문 편집 결과를 새 버전으로 저장
    POST /api/meeting          회의록 → 조문별 수정 제안
    GET  /api/download         Word(.docx) 생성, PDF는 인쇄 화면으로
    GET  /api/export           계약대장·버전대장 CSV
    GET  /api/template         표준 계약서 양식 Word 내려받기

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
from .meeting import build_proposals
from .models import RiskLevel
from .report import (
    ContractEntry,
    render_contract_docx,
    render_contract_index_csv,
    render_csv,
    render_docx,
    render_html,
    render_markdown,
    render_version_index_csv,
    render_workspace,
)
from .review import review_versions
from .templates import find as find_template
from .templates import read as read_template
from .versioning import VersionStore, build_timeline

UPLOAD_SUFFIXES = {".hwp", ".hwpx", ".docx", ".pdf"}
"""업로드로 받는 형식 — 한글·워드·PDF.

구형 .hwp는 olefile이 있어야 본문을 뽑을 수 있어, 등록 시점에 확인하고 막는다.
나중에 검토 단계에서 조용히 실패하면 원인을 찾기 어렵다.
"""

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
            status_override=config.store.status(contract_id),
        )
        entry.texts = _load_texts(config.store, contract_id, records)
        add_parties, remove_parties = config.store.split_party_specs(
            config.store.parties(contract_id)
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
                        add_parties=add_parties,
                        remove_parties=remove_parties,
                        rule_files=config.rule_files,
                        disable_rules=config.disable_rules,
                        progress=None,
                    )
                )
            except (FileNotFoundError, ValueError, RuntimeError):
                continue
        entries.append(entry)
    return entries


def _load_texts(store: VersionStore, contract_id: str, records) -> dict:
    """버전별 조문 원문. 파싱에 실패한 버전은 조용히 건너뛴다(비교는 계속 돌아야 한다)."""
    from .parsing import load_document

    texts: dict[str, list[tuple[str, str]]] = {}
    for record in records:
        try:
            document = load_document(store.resolve(contract_id, record.version))
        except (FileNotFoundError, ValueError, RuntimeError):
            continue
        texts[record.version] = [(c.heading, c.body) for c in document.clauses]
    return texts


def _result_for(config: ServerConfig, contract_id: str, before: str, after: str):
    add_parties, remove_parties = config.store.split_party_specs(
        config.store.parties(contract_id)
    )
    return review_versions(
        contract_id,
        before,
        after,
        store=config.store,
        settings=config.settings,
        views=config.views,
        min_level=config.min_level,
        add_parties=add_parties,
        remove_parties=remove_parties,
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

        if parsed.path == "/api/template":
            self._template(query)
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

        name = _safe(f"{contract_id}_{result.before_doc.version}-{result.after_doc.version}")
        if fmt == "docx":
            self._send(
                render_docx(result, contract_id),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=f"{name}.docx",
            )
            return
        if fmt == "pdf":
            # 한글 PDF는 폰트 임베딩이 필요해 직접 만들지 않는다. 인쇄용 화면을 띄워
            # 브라우저의 'PDF로 저장'을 쓰게 하는 편이 결과물도 정확하다.
            page = render_html(result).replace(
                "</body>", "<script>window.addEventListener('load',function(){window.print()});"
                "</script></body>"
            )
            self._send(page.encode("utf-8"), "text/html; charset=utf-8")
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
        self._send(
            text.encode("utf-8"),
            content_type,
            filename=f"{name}.{suffix}",
        )

    def _template(self, query: dict[str, list[str]]) -> None:
        """표준 계약서 양식을 Word로 내려준다."""
        template = find_template(query.get("id", [""])[0])
        if template is None:
            self._json({"ok": False, "error": "양식을 찾을 수 없습니다."}, status=404)
            return
        try:
            text = read_template(template)
        except FileNotFoundError as exc:
            self._json({"ok": False, "error": str(exc)}, status=404)
            return

        self._send(
            render_contract_docx(template.title, text),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{_safe(template.title)}.docx",
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
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/meeting":
            self._meeting()
            return
        if path == "/api/edit":
            self._edit()
            return
        if path != "/api/upload":
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
                suffix = Path(filename).suffix.lower()
                if suffix not in UPLOAD_SUFFIXES:
                    skipped.append(
                        {
                            "file": filename,
                            "reason": "한글(.hwp/.hwpx), Word(.docx), PDF만 올릴 수 있습니다.",
                        }
                    )
                    continue
                reason = _missing_reader(suffix)
                if reason:
                    skipped.append({"file": filename, "reason": reason})
                    continue
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

        specs = [s.strip() for s in (fields.get("parties") or "").split(",") if s.strip()]
        if specs:
            self.config.store.set_parties(contract_id, specs)

        self._json({"ok": bool(added), "added": added, "skipped": skipped})

    def _meeting(self) -> None:
        """회의록을 받아 조문별 수정 제안을 돌려준다."""
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json({"ok": False, "error": f"요청을 읽을 수 없습니다: {exc}"}, status=400)
            return

        contract_id = str(payload.get("contract_id", "")).strip()
        version = str(payload.get("version", "latest")).strip() or "latest"
        minutes = str(payload.get("minutes", "")).strip()
        if not contract_id or not minutes:
            self._json({"ok": False, "error": "계약과 회의 내용이 필요합니다."}, status=400)
            return

        from .llm.factory import create_backend
        from .parsing import load_document

        try:
            document = load_document(self.config.store.resolve(contract_id, version))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)
            return

        backend = create_backend(self.config.settings)
        proposals, items = build_proposals(document.clauses, minutes, backend)

        self._json(
            {
                "ok": True,
                "version": version,
                "unmatched": [i.text for i in items if i.clause_index is None],
                "clauses": [
                    {"heading": c.heading, "body": c.body} for c in document.clauses
                ],
                "proposals": [
                    {
                        "heading": p.heading,
                        "current": p.current,
                        "proposed": p.proposed,
                        "items": p.items,
                        "note": p.note,
                        "source": p.source,
                        "changed": p.changed,
                    }
                    for p in proposals
                ],
            }
        )

    def _edit(self) -> None:
        """조문 편집 결과를 새 버전으로 저장한다.

        등록된 원본은 해시로 고정돼 있어 덮어쓰지 않는다. 편집본은 다음 버전으로
        쌓이므로, 무엇을 고쳐서 상대방에게 보냈는지가 이력에 그대로 남는다.
        """
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json({"ok": False, "error": f"요청을 읽을 수 없습니다: {exc}"}, status=400)
            return

        contract_id = str(payload.get("contract_id", "")).strip()
        clauses = payload.get("clauses") or []
        if not contract_id or not clauses:
            self._json({"ok": False, "error": "계약 ID와 조문이 필요합니다."}, status=400)
            return

        text = _compose(clauses)
        base = str(payload.get("base_version", "")).strip()

        # 조문 일부만 보내면 나머지가 통째로 빠진 문서가 저장된다. 편집 화면은 늘
        # 전체 조문을 보내므로, 개수가 줄었다는 건 잘못된 호출이라고 본다.
        missing = _dropped_clauses(self.config.store, contract_id, base, len(clauses))
        if missing:
            self._json(
                {
                    "ok": False,
                    "error": f"{base}는 조문이 {missing}개인데 {len(clauses)}개만 전달됐습니다. "
                    "일부 조문이 사라질 수 있어 저장하지 않았습니다.",
                },
                status=400,
            )
            return

        # 아무것도 고치지 않고 저장하면 해시가 같아 중복으로 걸린다. 그 상황을
        # '중복 파일' 대신 '변경 없음'으로 알려 주는 편이 실제 상황에 맞다.
        if base:
            try:
                current = self.config.store.resolve(contract_id, base).read_text(
                    encoding="utf-8"
                )
            except (FileNotFoundError, OSError, UnicodeDecodeError):
                current = ""
            if current and "".join(current.split()) == "".join(text.split()):
                self._json(
                    {"ok": False, "error": f"{base}에서 바뀐 내용이 없어 새 버전을 만들지 않았습니다."},
                    status=400,
                )
                return
        label = str(payload.get("label", "")).strip() or f"{base} 편집본"

        temp_dir = Path(tempfile.mkdtemp(prefix="clausa-edit-"))
        try:
            path = temp_dir / f"{_safe(label)}.txt"
            path.write_text(text, encoding="utf-8")
            record = self.config.store.add(
                contract_id,
                path,
                label=label,
                note=str(payload.get("note", "")).strip() or f"{base} 조문 편집",
            )
        except (FileNotFoundError, ValueError) as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)
            return
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self._json({"ok": True, "version": record.version, "label": record.label})

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


def _dropped_clauses(store: VersionStore, contract_id: str, base: str, sent: int) -> int:
    """전달된 조문 수가 기준 버전보다 적으면 기준 버전의 조문 수를 돌려준다."""
    if not base:
        return 0
    try:
        from .parsing import load_document

        total = len(load_document(store.resolve(contract_id, base)).clauses)
    except (FileNotFoundError, ValueError, RuntimeError):
        return 0
    return total if sent < total else 0


def _compose(clauses: list[dict]) -> str:
    """편집된 조문 목록을 계약서 본문으로 되돌린다.

    제목 줄과 본문을 그대로 이어 붙이면 파서가 다시 같은 구조로 읽는다.
    전문(preamble)은 제목 줄 없이 본문만 쓴다.
    """
    blocks = []
    for clause in clauses:
        heading = str(clause.get("heading", "")).strip()
        body = str(clause.get("body", "")).strip()
        if heading in ("", "전문"):
            blocks.append(body)
        else:
            blocks.append(f"{heading}\n{body}" if body else heading)
    return "\n\n".join(b for b in blocks if b) + "\n"


def _missing_reader(suffix: str) -> str:
    """해당 형식을 읽는 데 필요한 선택 의존성이 빠져 있으면 사유를 돌려준다."""
    required = {".hwp": "olefile", ".docx": "docx", ".pdf": "pypdf"}.get(suffix)
    if not required:
        return ""

    import importlib.util

    if importlib.util.find_spec(required) is not None:
        return ""
    package = {"docx": "python-docx"}.get(required, required)
    return f"{suffix} 원본을 읽으려면 서버에 `pip install {package}` 가 필요합니다."


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
