# 계약서 비교 검토 AI (Contract Review AI)

두 버전의 계약서를 조문 단위로 대조하고, **SKT A.X 모델**(Hugging Face)로
조문마다 법무 코멘트를 생성하는 실무용 도구입니다.

- **입력**: `.hwpx` `.hwp` `.docx` `.pdf` `.txt` `.md`
- **처리**: 당사자 인식 → 조문 정렬 → 단어 단위 diff → 룰 기반 위험 탐지 → 당사자별 영향 추정 → LLM 코멘트
- **출력**: 단일 HTML 대시보드 · 마크다운 리포트 · JSON

> 생성 결과는 참고 자료이며 법률 자문이 아닙니다. 최종 판단은 변호사 검토를 거쳐야 합니다.

## 모델

기본값은 [`skt/A.X-3.1-Light`](https://huggingface.co/skt/A.X-3.1-Light) (7B · 32K 컨텍스트 · Apache-2.0)입니다.
한국어 계약 문언에 강하고, 32K 컨텍스트라 긴 조문도 잘리지 않습니다.

| 모델 | 규모 | 컨텍스트 | bf16 메모리 | 용도 |
|---|---|---|---|---|
| `skt/A.X-3.1-Light` (기본) | 7B | 32K | ~16GB | 사내 GPU 1장, 폐쇄망 |
| `skt/A.X-3.1` | 34B | 32K (YaRN 131K) | ~70GB | 정밀 검토 |
| `skt/A.X-4.0-Light` | 7B | 16K | ~16GB | 최신 경량 |
| `skt/A.X-4.0` | 72B | 128K | ~145GB | 장문 계약 일괄 |
| `skt/A.X-K2` | 692B MoE | — | — | API 전용 |

`--model` 또는 `.env`의 `CONTRACT_REVIEW_MODEL`로 교체합니다.

모델 연결만 따로 확인하려면:

```bash
python scripts/try_ax_model.py --backend local     # transformers 직접 로드
python scripts/try_ax_model.py --backend pipeline  # transformers.pipeline
python scripts/try_ax_model.py --backend hf_api    # GPU 불필요
```

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

포맷별 선택 의존성:

```bash
pip install python-docx pypdf olefile   # docx / pdf / 구형 hwp
```

`.hwpx`와 `.txt`는 표준 라이브러리만으로 읽습니다.

## 백엔드

| 백엔드 | 조건 | 비고 |
|---|---|---|
| `adot_biz` | `ADOT_BIZ_BASE_URL` + `ADOT_BIZ_API_KEY` | SKT A.Biz 사내 게이트웨이. 계약서가 사외로 나가지 않음 |
| `hf_api` | `.env`에 `HF_TOKEN` | GPU 불필요 |
| `local` | `torch` + `transformers>=4.46` + GPU | `AutoModelForCausalLM`을 직접 로드 |
| `pipeline` | 위와 동일 | `transformers.pipeline("text-generation", ...)` 경로 |
| `offline` | 없음 | 룰 엔진만으로 코멘트. 네트워크 0회 |
| `auto` (기본) | — | adot_biz → local → hf_api → offline 순으로 자동 강등 |

`local` 백엔드는 모델 카드 권장 방식(`apply_chat_template(..., return_dict=True)` →
`generate(**inputs)`)을 그대로 따르며, `attention_mask`를 함께 넘깁니다.

```bash
cp .env.example .env   # HF_TOKEN 입력
```

## 사용법

### 파일 두 개 직접 비교

```bash
contract-review 원본.hwpx 개정본.docx --party all -o out
```

### 버전 관리로 운영 (권장)

협상은 보통 3~5회 왕복합니다. 버전 저장소에 등록해 두면 원본이 sha256으로 고정되고,
대시보드의 **변경 이력** 탭에 협상 경과가 그대로 쌓입니다.

```bash
contract-review version add 물류계약 당사초안.hwpx --label "당사 초안"
contract-review version add 물류계약 상대방1차.hwpx --label "상대방 1차"
contract-review version add 물류계약 상대방2차.hwpx --label "상대방 2차"

contract-review version list 물류계약
contract-review history 물류계약

contract-review review --contract 물류계약 --from v1 --to latest --party all
```

### 당사자 지정

당사자는 `(이하 "병"이라 한다)` 정의 문언에서 자동 인식하지만, 정의 문언이 없는 각서·합의서나
예시 문구를 잘못 잡는 경우가 있어 수동으로 보정할 수 있습니다.

```bash
contract-review review a.hwpx b.hwpx \
  --add-party "병=주식회사 사아자:연대보증인" \
  --remove-party 정
```

`--add-party`는 형식이 `약칭[=상호][:역할]`이고, 이미 인식된 당사자면 상호·역할만 덮어씁니다.
둘 다 반복 지정할 수 있습니다.

### A.Biz(에이닷 비즈) 연계

SK 그룹 전사에 도입된 업무용 AI 에이전트 [A.Biz](https://news.sktelecom.com/209598)와는
두 계층에서 붙습니다.

**① 모델 계층** — A.Biz 사내 LLM 게이트웨이로 A.X를 호출합니다. 계약서 원문이 사외로
나가지 않으므로 법무 검토 요건을 만족합니다. `.env`만 채우면 됩니다.

```bash
ADOT_BIZ_BASE_URL=https://<사내-게이트웨이>/v1
ADOT_BIZ_API_KEY=<발급키>
ADOT_BIZ_MODEL=ax-3.1-light
```

**② 에이전트 계층** — A.Biz의 Agent Builder에 '계약 검토' 에이전트를 만들고, 이 도구를 그
에이전트가 호출하는 사내 API로 등록합니다. 임직원은 대화창에 계약서 두 개를 올리고
"이전 버전과 뭐가 달라졌는지 봐줘"라고 쓰면, 에이전트가 이 파이프라인을 돌려 의견서 링크를
돌려줍니다. 버전 저장소가 계약 ID 단위로 이력을 쌓으므로 3차·4차 수정본이 와도 같은 대화에서
"지난번 대비 뭐가 또 바뀌었나"를 이어서 물을 수 있습니다.

게이트웨이가 OpenAI 호환이 아니면 [`llm/adot_biz.py`](src/contract_review_ai/llm/adot_biz.py)
한 파일만 교체하면 됩니다. 나머지 파이프라인은 백엔드 종류를 알지 못합니다.

### 주요 옵션

| 옵션 | 설명 |
|---|---|
| `--party 을` / `--party all` | 특정 당사자 관점 또는 전 당사자 관점으로 코멘트 생성 |
| `--add-party` / `--remove-party` | 당사자 수동 추가·제외 |
| `--min-level medium` | 중위험 이상 조문만 LLM 호출 (비용·시간 절감) |
| `--backend hf_api` | 백엔드 강제 지정 |
| `--format html,md,json` | 출력 형식 선택 |
| `-o out` | 출력 폴더 |

고위험 변경이 하나라도 있으면 종료코드 `1`을 반환하므로, 결재 파이프라인의 게이트로 쓸 수 있습니다.

### 데모

```bash
python scripts/run_demo.py
```

3자 계약(갑·을·병) 샘플로 v1·v2를 등록하고 `out/dashboard.html`을 만듭니다. 네트워크를 쓰지 않습니다.

## 검토 의견서 (HTML)

외부 CDN·폰트·스크립트 의존이 전혀 없는 단일 HTML입니다(폐쇄망 반입 가능). 차트는 파이썬이 SVG로 직접 그립니다.
대형 로펌 의견서 톤 — 감청색 표제부에 금박 괘선, 명조 계열 제목, 미색 종이 바탕 — 으로 디자인했고
인쇄용 스타일(`@media print`)이 있어 탭 없이 전체가 한 문서로 출력됩니다.

지표 요약(변경·수정·신설·삭제·고위험·중위험 + 위험도 도넛)은 탭 위에 고정되어 어느 탭에서도 보입니다.

| 탭 | 내용 |
|---|---|
| **조문 대비** | 조문마다 **변경 요지**(삭제↔추가 대응표)를 먼저 보여주고, 좌우 대비 / 통합 대조를 전환할 수 있습니다. 위험도·구분·당사자·쟁점 필터와 전문 검색 제공 |
| **당사자 영향** | 당사자별 유·불리 막대 + 조문 × 당사자 매트릭스 — 다자간 계약에서 누가 무엇을 떠안는지 한 화면에 |
| **개정 연혁** | 버전 체인 타임라인 (v1→v2→v3 구간별 수정/신설/삭제/고위험) |

## 다자간 계약

`(이하 "갑"이라 한다)` 형태의 정의 문언을 파싱해 당사자를 자동 인식합니다. 갑·을뿐 아니라
병·정, 그리고 `(이하 "수급인"이라 한다)` 같은 역할 약칭도 잡습니다.

각 조문에서 당사자별로 **권리 표현**(…할 수 있다, 청구할 수 있다)과 **의무 표현**
(…하여야 한다, 부담한다, 배상한다)을 문장 단위로 세어 `권리 − 의무` 점수를 내고,
변경 전후 점수 차이로 유리/불리 방향을 추정합니다. 법적 판단이 아니라 **어디를 먼저 볼지
정하는 신호**이며, 리포트에도 그렇게 표기됩니다.

`--party all`을 주면 당사자 수만큼 관점별 코멘트를 각각 생성합니다.

## 위험 룰

LLM에 판단을 통째로 맡기지 않고, 결정론적 룰로 먼저 쟁점을 좁힙니다. 룰 결과는
(1) 프롬프트의 근거로 들어가고 (2) 모델이 놓치더라도 리포트에 그대로 남습니다.

손해배상(무제한 배상·책임 한도 삭제·간접손해 배제 삭제), 위약벌, 계약해지(일방적 해지·
시정기간 삭제), 지식재산권(귀속 변경·저작인격권 불행사), 면책·보상, 지체상금, 대금지급
(기일 연장·일방적 감액), 비밀유지, 준거법·분쟁해결, 자동갱신, 재위탁, 권리양도, 경업금지,
개인정보, 불가항력, 하자담보, 최혜대우, **연대보증(포괄근보증)**, 수치 변경(기간·요율·금액)
— 총 23종.

## 구조

```
contract-review-ai/
├── src/contract_review_ai/
│   ├── parsing/       hwpx·hwp·docx·pdf 로더, 조(條) 단위 분할
│   ├── parties/       당사자 인식, 당사자별 유·불리 영향 추정
│   ├── diffing/       문자 3-gram 유사도, 조문 정렬, 단어 diff
│   ├── risk/          룰 엔진 (23종)
│   ├── llm/           백엔드 (local A.X / HF API / offline) + JSON 파싱
│   ├── review/        프롬프트, 파이프라인 오케스트레이션
│   ├── versioning/    버전 저장소(sha256 고정), 변경 이력 타임라인
│   ├── report/        HTML 대시보드, 마크다운
│   └── cli.py         review / version / history 커맨드
├── data/samples/      3자 계약 샘플 (v1, v2)
├── scripts/run_demo.py
└── tests/
```

## 설계 원칙

- **파싱·정렬·diff·룰은 100% 결정론적** — 같은 입력이면 언제 돌려도 같은 결과. LLM은 코멘트 문장만 담당합니다.
- **코멘트마다 출처를 표기** — `offline(룰기반)`인지 `hf_api:skt/A.X-3.1-Light`인지 리포트에 남습니다.
- **모델 호출 실패는 조문 단위로 격리** — 한 조문이 실패해도 나머지 검토는 끝까지 진행됩니다.
- **위험도는 보수적으로** — 룰 판정과 LLM 판정 중 높은 쪽을 채택합니다.

## 테스트

```bash
pytest -q
```
