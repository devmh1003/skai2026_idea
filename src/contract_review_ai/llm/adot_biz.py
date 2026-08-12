"""SKT A.Biz(에이닷 비즈) 사내 게이트웨이 백엔드.

A.Biz는 SK 그룹이 전사 도입한 업무용 AI 에이전트 플랫폼으로, 사내 데이터를
붙여 맞춤 에이전트를 만드는 Agent Builder와 이를 공유하는 Agent Store를 갖는다.
이 도구는 두 지점에서 A.Biz에 붙는다.

1. **모델 계층** — 이 백엔드. A.Biz가 노출하는 사내 LLM 게이트웨이(OpenAI 호환)로
   A.X 계열 모델을 호출한다. 계약서 원문이 사외로 나가지 않는다는 점이 법무
   검토에서는 결정적이다.

2. **에이전트 계층** — Agent Builder에 '계약 검토' 에이전트를 만들고, 이 도구를
   그 에이전트가 호출하는 사내 API로 등록한다. 임직원은 A.Biz 대화창에 계약서
   두 개를 올리고 "이전 버전이랑 뭐가 달라졌는지 봐줘"라고 쓰면 되고, 결과로
   의견서 HTML 링크를 돌려받는다.

엔드포인트 규격은 사내망에서만 공개되므로, 실제 URL·인증 헤더는 환경변수로
주입한다. 게이트웨이가 OpenAI 호환이 아니라면 `extra_headers`/`extra_body`로
맞추거나 이 클래스만 갈아 끼우면 된다.

    ADOT_BIZ_BASE_URL=https://<사내-게이트웨이>/v1
    ADOT_BIZ_API_KEY=<발급키>
    ADOT_BIZ_MODEL=ax-3.1-light        # 게이트웨이가 쓰는 모델 별칭
    ADOT_BIZ_AGENT_ID=contract-review  # (선택) 에이전트 라우팅용
"""

from __future__ import annotations

import os

from ..config import Settings
from .openai_compat import OpenAICompatBackend


class AdotBizBackend(OpenAICompatBackend):
    def __init__(self, settings: Settings) -> None:
        base_url = os.getenv("ADOT_BIZ_BASE_URL", "").strip()
        api_key = os.getenv("ADOT_BIZ_API_KEY", "").strip()
        if not base_url or not api_key:
            raise RuntimeError(
                "A.Biz 백엔드에는 ADOT_BIZ_BASE_URL과 ADOT_BIZ_API_KEY가 필요합니다. "
                ".env를 확인하십시오."
            )

        model = os.getenv("ADOT_BIZ_MODEL", "").strip() or settings.model
        agent_id = os.getenv("ADOT_BIZ_AGENT_ID", "").strip()

        super().__init__(
            base_url=base_url,
            api_key=api_key,
            model=model,
            name=f"adot_biz:{model}",
            max_new_tokens=settings.max_new_tokens,
            temperature=settings.temperature,
            timeout=settings.timeout,
            extra_headers={"X-Agent-Id": agent_id} if agent_id else None,
        )
