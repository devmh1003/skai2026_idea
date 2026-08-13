"""체키 — 화면 구석을 돌아다니며 상황을 알려 주는 캐릭터.

계약 검토는 화면이 길고 숫자가 많아, 지금 무슨 일이 일어났는지 놓치기 쉽다.
체키는 화면 아래를 천천히 오가다가 상황이 바뀌면 그 자리에서 말을 건다.

    idle      대기·둘러보는 중
    scanning  분석·업로드·저장 진행 중
    alert     검토가 필요한 조항을 발견
    ok        처리 완료

캐릭터는 이미지 없이 CSS만으로 그린다(외부 리소스 0). 표정은 상태 클래스가 바꾼다.
"""

from __future__ import annotations

NAME = "체키"
TAGLINE = "계약 검토 도우미"

FACE_MARKUP = (
    '<div class="ck-body"></div><div class="ck-fold"></div>'
    '<div class="ck-eyes"><i></i><i></i></div><div class="ck-mouth"></div>'
    '<div class="ck-cheek l"></div><div class="ck-cheek r"></div>'
    '<div class="ck-lens"></div><div class="ck-badge">!</div><div class="ck-spark"></div>'
)

CSS = """
/* ── 체키 캐릭터 ─────────────────────────────────── */
.ck{--ink:#17191C;--red:#EA002C;--orange:#F47725}
@keyframes ck-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
@keyframes ck-blink{0%,90%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
@keyframes ck-scan{0%,100%{transform:rotate(-10deg)}50%{transform:rotate(10deg)}}
@keyframes ck-sweep{0%{top:-12%}100%{top:100%}}
@keyframes ck-shake{0%,100%{transform:rotate(-2.5deg)}50%{transform:rotate(2.5deg)}}
@keyframes ck-spark{0%,100%{opacity:.3;transform:scale(.8)}50%{opacity:1;transform:scale(1.15)}}
@keyframes ck-pop{from{opacity:0;transform:translateY(6px) scale(.96)}}

.ck-face{position:relative;width:var(--size,140px);height:var(--size,140px)}
.ck-face>*{position:absolute}
.ck-body{left:10%;top:5.7%;width:80%;height:80%;background:#fff;border:4px solid var(--ink);
border-radius:21%}
.ck-fold{left:71.4%;top:8.5%;width:18.5%;height:18.5%;background:#FFE3DA;
border-left:4px solid var(--ink);border-bottom:4px solid var(--ink);border-radius:0 100% 0 30%}
.ck-eyes{left:0;top:38%;width:100%;height:calc(var(--size,140px)*.14);display:flex;
align-items:center;justify-content:center;gap:18.5%}
/* 눈 크기는 캐릭터 크기 기준으로 잡는다. 부모 높이 기준 퍼센트는 부모가 auto라
   0으로 풀려 눈이 사라진다. */
.ck-eyes i{display:block;width:calc(var(--size,140px)*.12);height:calc(var(--size,140px)*.14);
border-radius:50%;background:var(--ink);animation:ck-blink 4.6s infinite}
.ck-mouth{left:45.7%;top:60%;width:14.3%;height:7%;border:4px solid var(--ink);border-top:none;
border-radius:0 0 50% 50%}
.ck-cheek{top:57%;width:12.8%;height:6.4%;border-radius:50%;background:#FFB3A7}
.ck-cheek.l{left:22.8%}.ck-cheek.r{left:68.5%}
.ck-lens,.ck-badge,.ck-spark{display:none}
.ck-face.scanning .ck-lens{display:block;left:-1.4%;top:44%;width:35.7%;height:35.7%;
border:7px solid var(--ink);border-radius:50%;background:rgba(244,119,37,.2);
animation:ck-scan 2.4s ease-in-out infinite}
.ck-face.alert .ck-badge{display:flex;left:-3%;top:-4%;width:26%;height:26%;background:var(--red);
border:4px solid var(--ink);border-radius:50%;color:#fff;font-size:calc(var(--size,140px)*.15);
font-weight:900;align-items:center;justify-content:center}
.ck-face.ok .ck-spark{display:block;right:1%;top:1%;width:10%;height:10%;background:var(--orange);
border-radius:50%;animation:ck-spark 1.6s ease-in-out infinite}

.ck-face.idle{animation:ck-bob 3s ease-in-out infinite}
.ck-face.ok{animation:ck-bob 2.2s ease-in-out infinite}
.ck-face.alert{animation:ck-shake .5s ease-in-out infinite}
.ck-face.scanning .ck-body{overflow:hidden}
.ck-face.scanning .ck-body::after{content:'';position:absolute;left:0;width:100%;height:16%;
background:linear-gradient(var(--orange),rgba(244,119,37,0));animation:ck-sweep 1.6s linear infinite}
.ck-face.scanning .ck-eyes i{height:calc(var(--size,140px)*.045);border-radius:3px;
animation:none}
.ck-face.scanning .ck-mouth{width:13%;height:13%;border:4px solid var(--ink);border-radius:50%;
top:58.5%;left:46.4%}
.ck-face.scanning .ck-cheek{display:none}
.ck-face.alert .ck-eyes i{width:calc(var(--size,140px)*.15);
height:calc(var(--size,140px)*.18)}
.ck-face.alert .ck-mouth{width:18.5%;height:13.5%;background:var(--ink);border:none;
border-radius:50%;left:41.4%;top:62.8%}
.ck-face.alert .ck-cheek{display:none}
.ck-face.ok .ck-eyes i{width:calc(var(--size,140px)*.17);height:calc(var(--size,140px)*.09);
background:none;border:3px solid var(--ink);border-bottom:none;border-radius:50% 50% 0 0}
.ck-face.ok .ck-mouth{width:15.7%;height:9.2%;background:var(--ink);border:none;
border-radius:0 0 50% 50%;left:42%;top:60%}

/* 작게 그리면 4px 테두리가 두꺼워 눈이 묻힌다. 작은 크기에서는 선을 얇게,
   눈·볼을 크게 잡아 표정이 남게 한다. */
.ck-face.sm .ck-body,.ck-face.sm .ck-mouth{border-width:3px}
.ck-face.sm .ck-fold{border-left-width:3px;border-bottom-width:3px}
.ck-face.sm .ck-eyes{gap:24%;height:calc(var(--size,140px)*.19)}
.ck-face.sm .ck-eyes i{width:calc(var(--size,140px)*.16);height:calc(var(--size,140px)*.19)}
.ck-face.sm .ck-mouth{top:62%;left:44%;width:16%;height:8%}
.ck-face.sm .ck-cheek{width:14%;height:7%;top:59%}
.ck-face.sm .ck-cheek.l{left:20%}.ck-face.sm .ck-cheek.r{left:66%}
.ck-face.sm.ok .ck-eyes i{width:calc(var(--size,140px)*.2);
height:calc(var(--size,140px)*.11);border-width:3px}
.ck-face.sm.alert .ck-eyes i{width:calc(var(--size,140px)*.19);
height:calc(var(--size,140px)*.22)}
.ck-face.sm.scanning .ck-eyes i{height:calc(var(--size,140px)*.055)}

/* ── 왼편을 오가는 동반자 ─────────────────────────── */
/* 본문은 오른쪽에 있으므로 화면 왼쪽 띠 안에서만 움직인다. */
.ck-buddy{position:fixed;left:14px;bottom:22px;z-index:40;display:flex;
flex-direction:column;align-items:flex-start;gap:8px;width:200px;
transition:transform 2.6s cubic-bezier(.4,0,.2,1);pointer-events:none}
.ck-buddy>*{pointer-events:auto}
.ck-buddy .ck-face{cursor:pointer;filter:drop-shadow(0 8px 18px rgba(23,25,28,.28))}
.ck-bubble{max-width:200px;order:-1;background:#fff;border:1px solid var(--line);
border-radius:14px 14px 14px 4px;
box-shadow:0 10px 28px rgba(23,25,28,.12);padding:11px 15px;font-size:13px;line-height:1.6;
color:var(--ink);animation:ck-pop .28s cubic-bezier(.22,1,.36,1) both}
.ck-bubble b{font-weight:700}
.ck-bubble[hidden]{display:none}
.ck-bubble .ck-close{float:right;margin:-2px -6px 0 8px;border:0;background:none;cursor:pointer;
color:#98a2b3;font-size:14px;line-height:1}
@media print{.ck-buddy{display:none}}

/* 사이드바 브랜드 얼굴 */
.brand .ck-face{flex:0 0 auto}
"""

JS = r"""
(function(){
  var buddy = document.querySelector('.ck-buddy');
  if (!buddy) return;
  var face = buddy.querySelector('.ck-face');
  var bubble = buddy.querySelector('.ck-bubble');
  var text = buddy.querySelector('.ck-text');
  var holdUntil = 0;

  function setState(state){
    face.className = 'ck-face sm ' + state;
  }

  // 상황별로 표정과 말이 함께 바뀐다. hold를 주면 그동안 산책 멘트가 끼어들지 않는다.
  function say(message, state, hold){
    if (message) {
      text.innerHTML = message;
      bubble.hidden = false;
    }
    setState(state || 'idle');
    holdUntil = Date.now() + (hold || 0);
  }
  window.checky = {say: say, state: setState};

  bubble.querySelector('.ck-close').addEventListener('click', function(){
    bubble.hidden = true;
  });
  face.addEventListener('click', function(){
    bubble.hidden = !bubble.hidden;
  });

  // 본문을 가리지 않도록 화면 왼쪽 띠 안에서만 오간다.
  var spots = [[0, 0], [26, -70], [6, -140], [30, -60]];
  var index = 0;
  function stroll(){
    index = (index + 1) % spots.length;
    var limit = Math.max(window.innerHeight - 220, 0);
    var move = spots[index];
    var y = Math.max(move[1], -limit);
    buddy.style.transform = 'translate(' + move[0] + 'px,' + y + 'px)';
  }
  stroll();
  setInterval(stroll, 9000);
  window.addEventListener('resize', stroll);

  // 아무 일도 없을 때 건네는 말 — 화면마다 다르게.
  var ambient = {
    dashboard: ['진행 중인 계약부터 볼까요?', '완료된 계약은 초록으로 표시했어요.'],
    contracts: ['계약을 고르면 버전과 검토 결과를 보여드려요.', '분류로 걸러서 볼 수 있어요.'],
    create: ['초안이 없으면 표준 양식부터 받아 가세요.', '당사자는 지금 정해 두면 계속 쓰여요.'],
    customers: ['계약별 당사자 명부예요.'],
    detail: ['버전을 누르면 그때 조문을 그대로 볼 수 있어요.', '회의록을 붙여 넣으면 조문을 찾아드려요.'],
    ledger: ['등록될 때마다 블록이 하나씩 쌓여요.', '중간을 고치면 뒤가 전부 어긋나요.'],
    result: ['왼쪽이 이전 문안, 오른쪽이 바뀐 문안이에요.',
             '문장 단위로 보고 있어요. 단어 단위로도 볼 수 있어요.']
  };
  var current = 'dashboard';
  window.checkyView = function(view){
    current = view;
    var lines = ambient[view];
    if (lines && Date.now() > holdUntil) say(lines[0], 'idle');
  };
  setInterval(function(){
    if (Date.now() < holdUntil) return;
    var lines = ambient[current];
    if (!lines || !lines.length) return;
    say(lines[Math.floor(Date.now() / 9000) % lines.length], 'idle');
  }, 15000);
})();
"""


def buddy_markup() -> str:
    """화면을 돌아다니는 체키."""
    return (
        '<div class="ck ck-buddy">'
        f'<div class="ck-face sm idle" style="--size:78px">{FACE_MARKUP}</div>'
        '<div class="ck-bubble"><button class="ck-close" title="닫기">×</button>'
        '<span class="ck-text">계약서를 올려주시면 조항을 훑어볼게요.</span></div>'
        "</div>"
    )


def brand_markup(size: int = 34) -> str:
    """사이드바 로고 자리에 들어가는 작은 체키."""
    return f'<div class="ck"><div class="ck-face idle" style="--size:{size}px">{FACE_MARKUP}</div></div>'
