"""핵심 파이프라인 단위 테스트 (네트워크·모델 없이 동작)."""

from __future__ import annotations

import zipfile

import pytest

from contract_review_ai.diffing import align_documents, similarity
from contract_review_ai.llm.base import parse_comment
from contract_review_ai.llm.offline import OfflineBackend
from contract_review_ai.models import ChangeStatus, Party, RiskLevel
from contract_review_ai.parsing import load_document, read_hwpx, segment_clauses
from contract_review_ai.parties import detect_parties, score_text
from contract_review_ai.report import render_html, render_markdown
from contract_review_ai.review import review_contracts
from contract_review_ai.risk import analyze_comparison
from contract_review_ai.versioning import VersionStore, build_timeline

V1 = """갑 주식회사(이하 "갑"이라 한다)와 을 주식회사(이하 "을"이라 한다)는 다음과 같이 정한다.

제1조(목적)
본 계약은 용역의 조건을 정한다.

제2조(손해배상)
배상 총액은 계약금액을 한도로 한다.
"""

V2 = """갑 주식회사(이하 "갑"이라 한다)와 을 주식회사(이하 "을"이라 한다)는 다음과 같이 정한다.

제1조(목적)
본 계약은 용역의 조건을 정한다.

제2조(손해배상)
을은 일체의 손해를 제한 없이 배상하여야 한다.

제3조(경업금지)
을은 계약 종료 후 3년간 경쟁 업체에 용역을 제공하지 아니한다.
"""


@pytest.fixture
def docs(tmp_path):
    before = tmp_path / "v1.txt"
    after = tmp_path / "v2.txt"
    before.write_text(V1, encoding="utf-8")
    after.write_text(V2, encoding="utf-8")
    return load_document(before), load_document(after)


# ---------------------------------------------------------------- 조문 분할


def test_segment_extracts_articles():
    clauses = segment_clauses(V1)
    numbers = [c.number for c in clauses]
    assert "1" in numbers and "2" in numbers
    assert any(c.title == "손해배상" for c in clauses)


def test_segment_keeps_preamble():
    clauses = segment_clauses(V1)
    assert clauses[0].number == "전문"


def test_segment_falls_back_to_numbered_items():
    text = "1. 첫째 항목입니다.\n2. 둘째 항목입니다.\n3. 셋째 항목입니다."
    assert len(segment_clauses(text)) >= 3


# ---------------------------------------------------------------- 유사도·정렬


def test_similarity_bounds():
    assert similarity("동일한 문장", "동일한 문장") == 1.0
    assert similarity("가나다라마", "전혀 다른 내용의 문장") < 0.3


def test_alignment_detects_change_kinds(docs):
    before, after = docs
    comparisons = align_documents(before, after)
    by_status = {}
    for comp in comparisons:
        by_status.setdefault(comp.status, []).append(comp.heading)

    assert any("목적" in h for h in by_status.get(ChangeStatus.UNCHANGED, []))
    assert any("손해배상" in h for h in by_status.get(ChangeStatus.MODIFIED, []))
    assert any("경업금지" in h for h in by_status.get(ChangeStatus.ADDED, []))


def test_alignment_matches_renumbered_clause(tmp_path):
    """조 번호가 밀려도 본문이 같으면 같은 조문으로 짝지어야 한다."""
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text(
        "제3조(비밀유지)\n각 당사자는 상대방의 영업비밀을 제3자에게 누설하지 아니한다.\n"
        "제4조(관할)\n서울중앙지방법원을 관할로 한다.\n",
        encoding="utf-8",
    )
    new.write_text(
        "제7조(비밀유지)\n각 당사자는 상대방의 영업비밀을 제3자에게 누설하지 아니한다.\n"
        "제8조(관할)\n서울중앙지방법원을 관할로 한다.\n",
        encoding="utf-8",
    )

    comparisons = align_documents(load_document(old), load_document(new))
    secrecy = next(c for c in comparisons if "비밀유지" in c.heading)
    assert secrecy.status is ChangeStatus.MODIFIED  # 제목의 조 번호만 달라짐
    assert secrecy.before is not None and secrecy.after is not None
    assert secrecy.similarity > 0.7


# ---------------------------------------------------------------- 룰


def test_alignment_matches_extended_title(tmp_path):
    """'검수' → '검수 및 지체상금'처럼 제목이 확장돼도 같은 조문으로 봐야 한다."""
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text(
        "제4조(검수)\n갑은 인도일로부터 14일 이내에 검수를 완료한다.\n", encoding="utf-8"
    )
    new.write_text(
        "제4조(검수 및 지체상금)\n갑은 인도일로부터 30일 이내에 검수를 완료한다.\n"
        "을이 인도 기일을 지키지 못한 경우 지체상금을 지급한다.\n",
        encoding="utf-8",
    )

    comparisons = align_documents(load_document(old), load_document(new))
    inspection = [c for c in comparisons if "검수" in c.heading]
    assert len(inspection) == 1
    assert inspection[0].status is ChangeStatus.MODIFIED


def test_rules_flag_unlimited_liability(docs):
    before, after = docs
    comparisons = align_documents(before, after)
    target = next(c for c in comparisons if "손해배상" in c.heading)
    codes = {f.code for f in analyze_comparison(target)}
    assert "LIAB-UNLIMITED" in codes
    assert "LIAB-CAP-REMOVED" in codes


def test_rules_ignore_unchanged_clause(docs):
    before, after = docs
    comparisons = align_documents(before, after)
    target = next(c for c in comparisons if c.status is ChangeStatus.UNCHANGED)
    assert analyze_comparison(target) == []


# ---------------------------------------------------------------- 당사자


def test_detect_parties_reads_alias_and_name():
    parties = detect_parties(V1)
    ids = [p.id for p in parties]
    assert ids[:2] == ["갑", "을"]
    assert parties[0].name.endswith("주식회사")


def test_detect_parties_handles_three_parties():
    text = (
        'A사(이하 "갑"이라 한다), B사(이하 "을"이라 한다) 및 '
        'C사(이하 "병"이라 한다)는 다음과 같이 약정한다.'
    )
    assert [p.id for p in detect_parties(text)] == ["갑", "을", "병"]


def test_parse_party_spec():
    from contract_review_ai.parties import parse_party_spec

    party = parse_party_spec("병=주식회사 사아자:연대보증인")
    assert (party.id, party.alias, party.name, party.role) == (
        "병", "병", "주식회사 사아자", "연대보증인"
    )
    assert parse_party_spec("정").alias == "정"


def test_apply_overrides_adds_and_removes():
    from contract_review_ai.parties import apply_overrides

    detected = detect_parties(V1)
    result = apply_overrides(detected, add=["병=주식회사 사아자:연대보증인"], remove=["갑"])
    ids = [p.id for p in result]
    assert "갑" not in ids
    assert "병" in ids
    assert next(p for p in result if p.id == "병").role == "연대보증인"


def test_apply_overrides_enriches_existing_party():
    from contract_review_ai.parties import apply_overrides

    result = apply_overrides(detect_parties(V1), add=["을=라마바 주식회사:수급인"])
    party = next(p for p in result if p.id == "을")
    assert party.name == "라마바 주식회사"
    assert party.role == "수급인"


def test_review_honours_party_overrides(tmp_path):
    before = tmp_path / "v1.txt"
    after = tmp_path / "v2.txt"
    before.write_text(V1, encoding="utf-8")
    after.write_text(V2, encoding="utf-8")

    result = review_contracts(
        before,
        after,
        backend=OfflineBackend(),
        progress=None,
        remove_parties=["갑"],
        add_parties=["병=주식회사 사아자:연대보증인"],
    )
    ids = [p.id for p in result.parties]
    assert ids == ["을", "병"]


def test_score_text_counts_obligation():
    party = Party(id="을", alias="을", name="")
    obligations, rights = score_text("을은 일체의 손해를 배상하여야 한다.", party)
    assert obligations == 1 and rights == 0


def test_impact_marks_adverse_party(docs):
    before, after = docs
    comparisons = align_documents(before, after)
    from contract_review_ai.parties import analyze_impacts

    target = next(c for c in comparisons if "손해배상" in c.heading)
    impacts = {i.party_id: i for i in analyze_impacts(target, [Party("을", "을", "")])}
    assert impacts["을"].verdict == "adverse"


# ---------------------------------------------------------------- HWPX


def _make_hwpx(path, paragraphs):
    ns = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
    body = "".join(f"<hp:p><hp:run><hp:t>{p}</hp:t></hp:run></hp:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", f"<hp:sec {ns}>{body}</hp:sec>")
    return path


def test_read_hwpx(tmp_path):
    path = _make_hwpx(tmp_path / "c.hwpx", ["제1조(목적)", "본 계약의 목적을 정한다."])
    text = read_hwpx(path)
    assert "제1조(목적)" in text and "목적을 정한다" in text


def test_load_hwpx_document(tmp_path):
    path = _make_hwpx(
        tmp_path / "c.hwpx",
        ['갑사(이하 "갑"이라 한다)와 을사(이하 "을"이라 한다)는 약정한다.',
         "제1조(목적)", "본 계약의 목적을 정한다.", "제2조(대금)", "갑은 대금을 지급한다."],
    )
    document = load_document(path)
    assert len(document.clauses) >= 2
    assert [p.id for p in document.parties][:2] == ["갑", "을"]


def test_unsupported_suffix(tmp_path):
    path = tmp_path / "c.xyz"
    path.write_text("내용", encoding="utf-8")
    with pytest.raises(ValueError):
        load_document(path)


# ---------------------------------------------------------------- 버전 관리


def test_version_store_roundtrip(tmp_path):
    store = VersionStore(tmp_path / "versions")
    src1 = tmp_path / "a.txt"
    src2 = tmp_path / "b.txt"
    src1.write_text(V1, encoding="utf-8")
    src2.write_text(V2, encoding="utf-8")

    first = store.add("계약A", src1, label="초안")
    second = store.add("계약A", src2, label="수정본")
    assert (first.version, second.version) == ("v1", "v2")
    assert store.resolve("계약A", "latest").name == second.file
    assert store.resolve("계약A", "v1").name == first.file
    assert store.contracts() == ["계약A"]


def test_version_store_rejects_duplicate_content(tmp_path):
    store = VersionStore(tmp_path / "versions")
    src = tmp_path / "a.txt"
    src.write_text(V1, encoding="utf-8")
    store.add("계약A", src, label="초안")
    with pytest.raises(ValueError):
        store.add("계약A", src, label="같은 파일")


def test_timeline_summarizes_steps(tmp_path):
    store = VersionStore(tmp_path / "versions")
    src1, src2 = tmp_path / "a.txt", tmp_path / "b.txt"
    src1.write_text(V1, encoding="utf-8")
    src2.write_text(V2, encoding="utf-8")
    store.add("계약A", src1)
    store.add("계약A", src2)

    steps = build_timeline(store, "계약A")
    assert len(steps) == 1
    assert steps[0].from_version == "v1" and steps[0].to_version == "v2"
    assert steps[0].added >= 1 and steps[0].high >= 1


# ---------------------------------------------------------------- LLM 파싱


def test_parse_comment_extracts_json():
    raw = '설명입니다 {"summary":"요약","issues":["A"],"risk_level":"high"} 끝'
    comment = parse_comment(raw, source="test", party_view="을")
    assert comment.summary == "요약"
    assert comment.issues == ["A"]
    assert comment.risk_level is RiskLevel.HIGH
    assert comment.party_view == "을"


def test_parse_comment_survives_garbage():
    comment = parse_comment("JSON이 아닌 응답", source="test")
    assert comment.summary == "JSON이 아닌 응답"
    assert comment.risk_level is RiskLevel.INFO


# ---------------------------------------------------------------- 통합


def test_review_end_to_end_offline(tmp_path):
    before = tmp_path / "v1.txt"
    after = tmp_path / "v2.txt"
    before.write_text(V1, encoding="utf-8")
    after.write_text(V2, encoding="utf-8")

    result = review_contracts(
        before, after, views=["all"], backend=OfflineBackend(), progress=None
    )

    assert result.risk_counts()["high"] >= 1
    assert len(result.parties) >= 2
    target = next(c for c in result.changed() if "손해배상" in c.heading)
    # 당사자 수만큼 관점별 코멘트가 붙어야 한다.
    assert len(target.comments) == len(result.parties)

    markdown = render_markdown(result)
    assert "계약서 비교 검토 리포트" in markdown
    assert "손해배상" in markdown

    page = render_html(result)
    assert "<!DOCTYPE html>" in page
    assert "조문 × 당사자 영향 매트릭스" in page
    assert "</script>" in page  # 데이터 블록이 문서를 깨뜨리지 않았는지
