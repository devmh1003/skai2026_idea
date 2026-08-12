"""예시 계약 10종을 만들어 버전 저장소에 등록한다.

    python scripts/make_samples.py            # 생성 + 등록
    python scripts/make_samples.py --files-only   # 파일만 생성
    python scripts/make_samples.py --reset        # 기존 등록분을 지우고 다시

계약 내용은 `sample_data.py`에 있다. 각 계약은 v1(당사 초안)에서 출발해 협상
왕복을 흉내 내며, 계약마다 협상이 멈춘 지점이 달라 현황 화면에 개시·진행중·완료가
섞여 나타난다. 조문을 신설·삭제하면 뒤 조문 번호가 밀리므로, 번호에 의존하지 않는
조문 정렬 로직도 함께 검증된다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sample_data import SAMPLES, Revision, Sample  # noqa: E402

from contract_review_ai.console import force_utf8  # noqa: E402
from contract_review_ai.versioning import VersionStore  # noqa: E402

SAMPLE_DIR = ROOT / "data" / "samples"
STORE_DIR = ROOT / "data" / "versions"


def render(preamble: str, clauses: list[tuple[str, str]]) -> str:
    lines = [preamble.strip(), ""]
    for index, (title, body) in enumerate(clauses, start=1):
        lines.append(f"제{index}조({title})")
        lines.append(body.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def apply_revision(clauses: list[tuple[str, str]], rev: Revision) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for title, body in clauses:
        if title in rev.drops:
            continue
        out.append((rev.renames.get(title, title), rev.edits.get(title, body)))
    out.extend(rev.adds)
    return out


def build(sample: Sample) -> list[tuple[Path, str, str]]:
    """(파일 경로, 라벨, 메모) 목록. 협상이 도달한 회차까지만 만든다."""
    folder = SAMPLE_DIR / sample.slug
    folder.mkdir(parents=True, exist_ok=True)

    clauses = list(sample.clauses)
    rows = [(folder / "v1.txt", "당사 초안", "최초 작성본", render(sample.preamble, clauses))]
    for index, revision in enumerate(sample.revisions, start=2):
        clauses = apply_revision(clauses, revision)
        rows.append(
            (
                folder / f"v{index}.txt",
                revision.label,
                revision.note,
                render(sample.preamble, clauses),
            )
        )

    rows = rows[: sample.registered]
    keep = {path for path, _, _, _ in rows}
    for path, _, _, text in rows:
        path.write_text(text, encoding="utf-8")
    for stale in folder.glob("v*.txt"):
        if stale not in keep:
            stale.unlink()

    return [(path, label, note) for path, label, note, _ in rows]


def main() -> int:
    force_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--files-only", action="store_true", help="등록 없이 파일만 생성")
    parser.add_argument("--reset", action="store_true", help="기존 등록분을 지우고 다시 등록")
    args = parser.parse_args()

    if args.reset and STORE_DIR.exists():
        shutil.rmtree(STORE_DIR)
        print("기존 버전 저장소를 비웠습니다.")

    store = VersionStore(STORE_DIR)
    stages = {1: "개시", 7: "완료"}
    for sample in SAMPLES:
        rows = build(sample)
        stage = stages.get(sample.registered, "진행중")
        print(f"{sample.title} ({sample.contract_id}) — {len(rows)}개 버전 · {stage}")

        if args.files_only:
            continue
        for path, label, note in rows:
            try:
                record = store.add(
                    sample.contract_id,
                    path,
                    label=label,
                    note=note,
                    title=sample.title,
                    category=sample.category,
                )
                print(f"  {record.version}  {label}")
            except ValueError as exc:
                print(f"  건너뜀: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
