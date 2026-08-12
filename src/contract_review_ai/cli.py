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
from .models import RiskLevel
from .report import render_html, render_markdown
from .review import review_contracts, review_versions
from .versioning import VersionStore, build_timeline

_LEVELS = {
    "high": RiskLevel.HIGH,
    "medium": RiskLevel.MEDIUM,
    "low": RiskLevel.LOW,
    "info": RiskLevel.INFO,
}
_SUBCOMMANDS = {"review", "version", "history"}


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
        "--min-level",
        choices=list(_LEVELS),
        default="info",
        help="이 위험도 이상인 변경 조문만 LLM 코멘트 생성 (기본: info = 전부)",
    )
    review.add_argument("--format", default="md,html,json", help="출력 형식 (md,html,json)")
    review.add_argument("--max-new-tokens", type=int, default=None, help="조문당 생성 토큰 상한")
    review.add_argument("-q", "--quiet", action="store_true", help="진행 로그 숨김")

    version = sub.add_parser("version", help="계약서 버전 관리")
    version_sub = version.add_subparsers(dest="version_command", required=True)

    add = version_sub.add_parser("add", help="새 버전 등록")
    add.add_argument("contract_id")
    add.add_argument("file")
    add.add_argument("--label", default="", help="버전 라벨 (예: '상대방 2차 수정본')")
    add.add_argument("--note", default="", help="메모")
    add.add_argument("--title", default="", help="계약 제목 (최초 등록 시)")

    listing = version_sub.add_parser("list", help="등록된 버전 조회")
    listing.add_argument("contract_id", nargs="?", default="")

    history = sub.add_parser("history", help="버전 체인 전체의 변경 이력 요약")
    history.add_argument("contract_id")

    return parser


def main(argv: list[str] | None = None) -> int:
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
    unknown = formats - {"md", "html", "json"}
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
    stem = f"{result.before_doc.name}__vs__{result.after_doc.name}"
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
                args.contract_id, args.file, label=args.label, note=args.note, title=args.title
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


if __name__ == "__main__":
    raise SystemExit(main())
