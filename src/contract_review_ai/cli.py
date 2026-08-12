"""커맨드라인 진입점.

    contract-review review 원본.hwpx 개정본.docx
    contract-review review --contract 물류계약 --from v1 --to latest --party all
    contract-review version add 물류계약 상대방_수정본.hwpx --label "상대방 2차"
    contract-review version list 물류계약
    contract-review history 물류계약
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import BACKENDS, DEFAULT_MODEL, Settings
from .console import force_utf8
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
from .review import review_contracts, review_versions
from .risk import RuleFileError, build_ruleset, export_rules
from .versioning import VersionStore, build_timeline

_LEVELS = {
    "high": RiskLevel.HIGH,
    "medium": RiskLevel.MEDIUM,
    "low": RiskLevel.LOW,
    "info": RiskLevel.INFO,
}
_SUBCOMMANDS = {
    "review",
    "version",
    "history",
    "rules",
    "workspace",
    "new",
    "attach",
    "serve",
}
FORMATS = ("md", "html", "json", "csv")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contract-review",
        description="계약서 버전을 비교하고 A.X 모델로 법무 코멘트를 생성합니다.",
    )
    parser.add_argument(
        "--store", default="data/versions", help="버전 저장소 경로 (기본: data/versions)"
    )
    sub = parser.add_subparsers(dest="command")

    review = sub.add_parser("review", help="두 계약서를 비교하고 리포트를 생성")
    review.add_argument("before", nargs="?", help="원본 계약서 (.hwpx/.hwp/.docx/.pdf/.txt)")
    review.add_argument("after", nargs="?", help="개정본 계약서")
    review.add_argument("--contract", default="", help="버전 저장소의 계약 ID로 비교")
    review.add_argument("--from", dest="from_version", default="first", help="시작 버전 (기본: first)")
    review.add_argument("--to", dest="to_version", default="latest", help="대상 버전 (기본: latest)")
    review.add_argument("-o", "--out", default="out", help="리포트 출력 폴더 (기본: out)")
    review.add_argument("--backend", choices=BACKENDS, default=None, help="코멘트 백엔드")
    review.add_argument("--model", default=None, help=f"HF 모델 ID (기본: {DEFAULT_MODEL})")
    review.add_argument(
        "--party",
        default="",
        help="코멘트 관점. 당사자 약칭을 콤마로 구분하거나 all (예: --party 을 / --party all)",
    )
    review.add_argument(
        "--add-party",
        action="append",
        default=[],
        metavar="약칭[=상호][:역할]",
        help="당사자 추가·보정. 반복 지정 가능 (예: --add-party '병=주식회사 사아자:연대보증인')",
    )
    review.add_argument(
        "--remove-party",
        action="append",
        default=[],
        metavar="약칭",
        help="자동 인식된 당사자 제외. 반복 지정 가능 (예: --remove-party 병)",
    )
    review.add_argument(
        "--rules",
        action="append",
        default=[],
        metavar="파일",
        help="사용자 룰 파일(.json/.toml)을 내장 룰에 얹습니다. 반복 지정 가능",
    )
    review.add_argument(
        "--disable-rule",
        action="append",
        default=[],
        metavar="코드",
        help="특정 룰 해제 (예: --disable-rule MFN --disable-rule NUMERIC-CHANGE)",
    )
    review.add_argument(
        "--min-level",
        choices=list(_LEVELS),
        default="info",
        help="이 위험도 이상인 변경 조문만 LLM 코멘트 생성 (기본: info = 전부)",
    )
    review.add_argument(
        "--format",
        default="md,html,json",
        help="출력 형식. md,html,json,csv 중 콤마로 조합하거나 all (기본: md,html,json)",
    )
    review.add_argument("--max-new-tokens", type=int, default=None, help="조문당 생성 토큰 상한")
    review.add_argument("-q", "--quiet", action="store_true", help="진행 로그 숨김")

    new = sub.add_parser("new", help="계약을 새로 만들고 첫 원본을 첨부")
    new.add_argument("contract_id", help="계약 ID (예: 2026-물류-001)")
    new.add_argument("files", nargs="*", help="첨부할 계약서 파일 (여러 개면 v1,v2… 순서로)")
    new.add_argument("--title", default="", help="계약명")
    new.add_argument("--category", default="", help="분류 (예: 용역·도급)")
    new.add_argument("--label", action="append", default=[], help="파일별 버전 라벨")

    attach = sub.add_parser("attach", help="기존 계약에 파일을 버전으로 첨부")
    attach.add_argument("contract_id")
    attach.add_argument("files", nargs="+")
    attach.add_argument("--label", action="append", default=[], help="파일별 버전 라벨")
    attach.add_argument("--note", default="", help="메모")

    version = sub.add_parser("version", help="계약서 버전 관리")
    version_sub = version.add_subparsers(dest="version_command", required=True)

    add = version_sub.add_parser("add", help="새 버전 등록")
    add.add_argument("contract_id")
    add.add_argument("file")
    add.add_argument("--label", default="", help="버전 라벨 (예: '상대방 2차 수정본')")
    add.add_argument("--note", default="", help="메모")
    add.add_argument("--title", default="", help="계약 제목 (최초 등록 시)")
    add.add_argument("--category", default="", help="계약 분류 (예: 용역, 공급, 임대차, 비밀유지)")

    listing = version_sub.add_parser("list", help="등록된 버전 조회")
    listing.add_argument("contract_id", nargs="?", default="")

    history = sub.add_parser("history", help="버전 체인 전체의 변경 이력 요약")
    history.add_argument("contract_id")

    portal = sub.add_parser("workspace", help="계약·버전·검토를 묶은 워크스페이스 생성")
    portal.add_argument("contract_id", nargs="*", help="대상 계약 ID (생략 시 전체)")
    portal.add_argument("-o", "--out", default="out", help="출력 폴더")
    portal.add_argument("--backend", choices=BACKENDS, default=None)
    portal.add_argument("--model", default=None)
    portal.add_argument("--party", default="", help="코멘트 관점 (약칭 콤마 구분 또는 all)")
    portal.add_argument(
        "--min-level", choices=list(_LEVELS), default="medium",
        help="LLM 코멘트를 생성할 최소 위험도 (기본: medium — 계약 수가 많아 기본값이 높습니다)",
    )
    portal.add_argument(
        "--pairs", choices=("adjacent", "all", "latest"), default="adjacent",
        help="비교 조합. adjacent=연속 버전(+최초→최신), all=모든 조합, latest=최초→최신만",
    )
    portal.add_argument("--rules", action="append", default=[])
    portal.add_argument("--disable-rule", action="append", default=[])
    portal.add_argument(
        "--export", default="", help="추가 내보내기: csv (계약·버전 대장과 조문 표)"
    )
    portal.add_argument("-q", "--quiet", action="store_true")

    serve_cmd = sub.add_parser("serve", help="브라우저에서 업로드·내려받기까지 되는 로컬 서버")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8000)
    serve_cmd.add_argument("--backend", choices=BACKENDS, default=None)
    serve_cmd.add_argument("--model", default=None)
    serve_cmd.add_argument("--party", default="", help="코멘트 관점 (약칭 콤마 구분 또는 all)")
    serve_cmd.add_argument("--min-level", choices=list(_LEVELS), default="medium")
    serve_cmd.add_argument("--pairs", choices=("adjacent", "all", "latest"), default="adjacent")
    serve_cmd.add_argument("--rules", action="append", default=[])
    serve_cmd.add_argument("--disable-rule", action="append", default=[])

    rules = sub.add_parser("rules", help="쟁점 룰 조회·내보내기")
    rules_sub = rules.add_subparsers(dest="rules_command", required=True)

    rules_list = rules_sub.add_parser("list", help="적용 중인 룰 목록")
    rules_list.add_argument("--rules", action="append", default=[], help="사용자 룰 파일")
    rules_list.add_argument("--disable-rule", action="append", default=[], help="해제할 룰 코드")

    rules_export = rules_sub.add_parser("export", help="현재 룰셋을 파일로 내보내기")
    rules_export.add_argument("file", help="저장할 경로 (.json)")
    rules_export.add_argument("--rules", action="append", default=[], help="사용자 룰 파일")
    rules_export.add_argument("--disable-rule", action="append", default=[], help="해제할 룰 코드")

    return parser


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    # `contract-review a.hwpx b.hwpx` 처럼 서브커맨드를 생략해도 review로 본다.
    if argv and argv[0] not in _SUBCOMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "review")

    args = build_parser().parse_args(argv)
    store = VersionStore(args.store)

    if args.command == "version":
        return _cmd_version(args, store)
    if args.command == "history":
        return _cmd_history(args, store)
    if args.command == "rules":
        return _cmd_rules(args)
    if args.command == "workspace":
        return _cmd_workspace(args, store)
    if args.command in ("new", "attach"):
        return _cmd_attach(args, store)
    if args.command == "serve":
        return _cmd_serve(args, store)
    if args.command == "review":
        return _cmd_review(args, store)

    build_parser().print_help()
    return 2


# ---------------------------------------------------------------- review


def _cmd_review(args, store: VersionStore) -> int:
    settings = Settings.from_env()
    if args.backend:
        settings.backend = args.backend
    if args.model:
        settings.model = args.model
    if args.max_new_tokens:
        settings.max_new_tokens = args.max_new_tokens

    formats = {f.strip().lower() for f in args.format.split(",") if f.strip()}
    if "all" in formats:
        formats = set(FORMATS)
    unknown = formats - set(FORMATS)
    if unknown:
        print(f"[오류] 알 수 없는 출력 형식: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    views = [v.strip() for v in args.party.split(",") if v.strip()]
    progress = None if args.quiet else (lambda m: print(m, file=sys.stderr))
    common = {
        "settings": settings,
        "views": views,
        "min_level": _LEVELS[args.min_level],
        "progress": progress,
        "add_parties": args.add_party,
        "remove_parties": args.remove_party,
        "rule_files": args.rules,
        "disable_rules": args.disable_rule,
    }

    try:
        if args.contract:
            result = review_versions(
                args.contract, args.from_version, args.to_version, store=store, **common
            )
        else:
            if not (args.before and args.after):
                print(
                    "[오류] 비교할 파일 두 개 또는 --contract 를 지정하십시오.", file=sys.stderr
                )
                return 2
            result = review_contracts(args.before, args.after, **common)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _export_stem(result)
    written: list[Path] = []

    renderers = {
        "md": (".md", render_markdown),
        "html": (".html", render_html),
    }
    for key, (suffix, render) in renderers.items():
        if key in formats:
            path = out_dir / f"{stem}{suffix}"
            path.write_text(render(result), encoding="utf-8")
            written.append(path)
    if "json" in formats:
        path = out_dir / f"{stem}.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written.append(path)
    if "csv" in formats:
        path = out_dir / f"{stem}.csv"
        path.write_text(render_csv(result), encoding="utf-8")
        written.append(path)

    risks = result.risk_counts()
    print(
        f"변경 {len(result.changed())}건 "
        f"(높음 {risks['high']} / 중간 {risks['medium']} / 낮음 {risks['low']})"
    )
    for path in written:
        print(f"  → {path}")

    # 고위험 변경이 있으면 종료코드 1 — 승인 파이프라인의 게이트로 쓸 수 있게.
    return 1 if risks["high"] else 0


# ---------------------------------------------------------------- version


def _cmd_version(args, store: VersionStore) -> int:
    if args.version_command == "add":
        try:
            record = store.add(
                args.contract_id,
                args.file,
                label=args.label,
                note=args.note,
                title=args.title,
                category=args.category,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"[오류] {exc}", file=sys.stderr)
            return 1
        print(f"{args.contract_id} · {record.version} 등록: {record.label}")
        print(f"  파일 {record.file}")
        print(f"  sha256 {record.sha256[:16]}…")
        return 0

    if not args.contract_id:
        contracts = store.contracts()
        if not contracts:
            print("등록된 계약이 없습니다.")
            return 0
        for contract in contracts:
            records = store.versions(contract)
            latest = records[-1].version if records else "-"
            print(f"{contract}  ({len(records)}개 버전, 최신 {latest})")
        return 0

    records = store.versions(args.contract_id)
    if not records:
        print(f"{args.contract_id}: 등록된 버전이 없습니다.")
        return 1
    print(f"{args.contract_id} — {len(records)}개 버전")
    for record in records:
        note = f"  // {record.note}" if record.note else ""
        print(f"  {record.version:>4}  {record.imported_at}  {record.label}{note}")
        print(f"        {record.file}  sha256:{record.sha256[:16]}…")
    return 0


# ---------------------------------------------------------------- history


def _cmd_history(args, store: VersionStore) -> int:
    try:
        steps = build_timeline(store, args.contract_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 1

    if not steps:
        print(f"{args.contract_id}: 비교할 버전이 2개 미만입니다.")
        return 0

    print(f"{args.contract_id} 변경 이력")
    for step in steps:
        print(
            f"  {step.from_version} → {step.to_version}: "
            f"수정 {step.modified} · 신설 {step.added} · 삭제 {step.deleted} "
            f"· 고위험 {step.high} · 중위험 {step.medium}"
        )
        if step.headings:
            print(f"      주요 변경: {', '.join(step.headings)}")
    return 0


# ---------------------------------------------------------------- workspace


def _version_pairs(versions: list[str], mode: str) -> list[tuple[str, str]]:
    """비교할 (이전, 이후) 버전 조합."""
    if len(versions) < 2:
        return []
    if mode == "latest":
        return [(versions[0], versions[-1])]
    if mode == "all":
        return [(a, b) for i, a in enumerate(versions) for b in versions[i + 1 :]]

    pairs = list(zip(versions, versions[1:], strict=False))
    if len(versions) > 2:
        pairs.append((versions[0], versions[-1]))  # 누적 변화도 한 번에 보게
    return pairs


def _cmd_workspace(args, store: VersionStore) -> int:
    settings = Settings.from_env()
    if args.backend:
        settings.backend = args.backend
    if args.model:
        settings.model = args.model

    targets = args.contract_id or store.contracts()
    if not targets:
        print("등록된 계약이 없습니다. version add 로 먼저 등록하십시오.", file=sys.stderr)
        return 1

    views = [v.strip() for v in args.party.split(",") if v.strip()]
    say = (lambda _: None) if args.quiet else (lambda m: print(m, file=sys.stderr))
    contracts: list[ContractEntry] = []

    for contract_id in targets:
        records = store.versions(contract_id)
        pairs = _version_pairs([r.version for r in records], args.pairs)
        if not pairs:
            say(f"{contract_id}: 버전이 2개 미만이라 건너뜁니다.")
            continue

        entry = ContractEntry(
            contract_id=contract_id,
            title=store.title(contract_id),
            category=store.category(contract_id),
            versions=records,
            timeline=build_timeline(store, contract_id),
        )
        for before, after in pairs:
            say(f"[{contract_id}] {before} → {after} 검토 중…")
            try:
                entry.results.append(
                    review_versions(
                        contract_id,
                        before,
                        after,
                        store=store,
                        settings=settings,
                        views=views,
                        min_level=_LEVELS[args.min_level],
                        rule_files=args.rules,
                        disable_rules=args.disable_rule,
                        progress=None,
                    )
                )
            except (FileNotFoundError, ValueError, RuntimeError) as exc:
                say(f"  건너뜀: {exc}")
        if entry.results:
            contracts.append(entry)

    if not contracts:
        print("[오류] 비교 가능한 계약이 없습니다.", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "workspace.html"
    path.write_text(render_workspace(contracts), encoding="utf-8")

    written = [path]
    if "csv" in {f.strip().lower() for f in args.export.split(",") if f.strip()}:
        written += _write_workspace_csv(contracts, out_dir)

    total = sum(len(c.results) for c in contracts)
    high = sum(c.high for c in contracts)
    print(f"계약 {len(contracts)}건 · 비교본 {total}개 · 고위험 {high}건")
    for item in written:
        print(f"  → {item}")
    return 0


def _write_workspace_csv(contracts: list[ContractEntry], out_dir: Path) -> list[Path]:
    """계약 대장·버전 대장·조문 표를 한 번에 떨어뜨린다(감사·보고용)."""
    index = out_dir / "계약대장.csv"
    index.write_text(
        render_contract_index_csv(
            [
                {
                    "contract_id": c.contract_id,
                    "title": c.label,
                    "category": c.category,
                    "versions": len(c.versions),
                    "latest": c.latest,
                    "high": c.high,
                    "updated_at": c.updated_at,
                }
                for c in contracts
            ]
        ),
        encoding="utf-8",
    )

    versions = out_dir / "버전대장.csv"
    versions.write_text(
        render_version_index_csv(
            [
                {
                    "contract_id": c.contract_id,
                    "title": c.label,
                    "version": r.version,
                    "label": r.label,
                    "imported_at": r.imported_at,
                    "sha256": r.sha256,
                    "note": r.note,
                    "file": r.file,
                }
                for c in contracts
                for r in c.versions
            ]
        ),
        encoding="utf-8",
    )

    written = [index, versions]
    clause_dir = out_dir / "조문표"
    clause_dir.mkdir(exist_ok=True)
    for contract in contracts:
        for result in contract.results:
            path = clause_dir / f"{_export_stem(result, contract.contract_id)}.csv"
            path.write_text(render_csv(result, contract.contract_id), encoding="utf-8")
            written.append(path)
    return written


def _export_stem(result, contract_id: str = "") -> str:
    """내보내기 파일명. 어떤 계약의 몇 번 버전 비교인지 이름만 보고 알 수 있어야 한다.

        2026-물류-001_v1-v3.csv
        용역계약서_v1__vs__용역계약서_v2.csv   (버전 저장소를 쓰지 않은 경우)
    """
    contract_id = contract_id or result.contract_id
    before, after = result.before_doc.version, result.after_doc.version
    if contract_id and before and after:
        return _safe_name(f"{contract_id}_{before}-{after}")
    if before and after:
        return _safe_name(f"{result.before_doc.name}_{before}-{after}")
    return _safe_name(f"{result.before_doc.name}__vs__{result.after_doc.name}")


def _safe_name(text: str) -> str:
    import re

    return re.sub(r'[\/:*?"<>|]+', "_", text).replace(" ", "_")


# ---------------------------------------------------------------- serve


def _cmd_serve(args, store: VersionStore) -> int:
    from .serve import ServerConfig, serve

    settings = Settings.from_env()
    if args.backend:
        settings.backend = args.backend
    if args.model:
        settings.model = args.model

    config = ServerConfig(
        store=store,
        settings=settings,
        views=[v.strip() for v in args.party.split(",") if v.strip()],
        min_level=_LEVELS[args.min_level],
        pairs=args.pairs,
        rule_files=args.rules,
        disable_rules=args.disable_rule,
    )
    return serve(config, host=args.host, port=args.port)


# ---------------------------------------------------------------- rules


def _cmd_rules(args) -> int:
    try:
        rules, disabled = build_ruleset(args.rules, args.disable_rule)
    except RuleFileError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 1

    if args.rules_command == "export":
        path = export_rules(rules, args.file)
        print(f"룰 {len(rules)}종을 {path}에 저장했습니다.")
        print("파일을 편집한 뒤 --rules 옵션으로 지정하십시오.")
        return 0

    print(f"적용 중인 룰 {len(rules)}종" + (f" (해제 {len(disabled)}종)" if disabled else ""))
    by_category: dict[str, list] = {}
    for rule in rules:
        by_category.setdefault(rule.category, []).append(rule)

    for category in sorted(by_category):
        print(f"\n[{category}]")
        for rule in by_category[category]:
            print(f"  {rule.level.label:<3} {rule.code:<22} {rule.message[:56]}")
    if disabled:
        print(f"\n해제됨: {', '.join(sorted(disabled))}")
    return 0


# ---------------------------------------------------------------- new / attach


def _cmd_attach(args, store: VersionStore) -> int:
    """계약을 만들거나, 기존 계약에 파일을 버전으로 붙인다."""
    creating = args.command == "new"
    files = list(args.files)
    if not files:
        if not creating:
            print("[오류] 첨부할 파일을 지정하십시오.", file=sys.stderr)
            return 2
        # 파일 없이 계약 껍데기만 만드는 경우
        folder = store.root / _safe_id(args.contract_id)
        folder.mkdir(parents=True, exist_ok=True)
        manifest = store.load(args.contract_id)
        manifest.update(
            {
                "contract_id": args.contract_id,
                "title": args.title or args.contract_id,
                "category": args.category,
                "versions": manifest.get("versions", []),
            }
        )
        store.manifest_path(args.contract_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{args.contract_id} 계약을 만들었습니다. attach 로 원본을 첨부하십시오.")
        return 0

    labels = list(args.label)
    added = 0
    for index, path in enumerate(files):
        label = labels[index] if index < len(labels) else Path(path).stem
        try:
            record = store.add(
                args.contract_id,
                path,
                label=label,
                note=getattr(args, "note", ""),
                title=getattr(args, "title", ""),
                category=getattr(args, "category", ""),
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"[건너뜀] {path}: {exc}", file=sys.stderr)
            continue
        print(f"{args.contract_id} · {record.version} 첨부: {record.label}")
        print(f"  {record.file}  sha256:{record.sha256[:16]}…")
        added += 1

    if not added:
        return 1
    print(f"총 {added}개 파일을 첨부했습니다.")
    return 0


def _safe_id(name: str) -> str:
    from .versioning.store import _safe

    return _safe(name)


if __name__ == "__main__":
    raise SystemExit(main())
