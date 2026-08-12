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
.ck-eyes{left:0;top:40%;width:100%;display:flex;justify-content:center;gap:18.5%}
.ck-eyes i{display:block;width:11%;height:13%;border-radius:50%;background:var(--ink);
animation:ck-blink 4.6s infinite}
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
.ck-face.scanning .ck-eyes i{height:3.5%;border-radius:3px;animation:none}
.ck-face.scanning .ck-mouth{width:13%;height:13%;border:4px solid var(--ink);border-radius:50%;
top:58.5%;left:46.4%}
.ck-face.scanning .ck-cheek{display:none}
.ck-face.alert .ck-eyes i{width:13.5%;height:16.4%}
.ck-face.alert .ck-mouth{width:18.5%;height:13.5%;background:var(--ink);border:none;
border-radius:50%;left:41.4%;top:62.8%}
.ck-face.alert .ck-cheek{display:none}
.ck-face.ok .ck-eyes i{width:15.7%;height:8.5%;background:none;border:4px solid var(--ink);
border-bottom:none;border-radius:50% 50% 0 0}
.ck-face.ok .ck-mouth{width:15.7%;height:9.2%;background:var(--ink);border:none;
border-radius:0 0 50% 50%;left:42%;top:60%}

/* ── 돌아다니는 동반자 ────────────────────────────── */
.ck-buddy{position:fixed;bottom:20px;left:0;z-index:40;display:flex;align-items:flex-end;gap:10px;
transition:transform 2.4s cubic-bezier(.4,0,.2,1);pointer-events:none}
.ck-buddy>*{pointer-events:auto}
.ck-buddy .ck-face{cursor:pointer;filter:drop-shadow(0 6px 14px rgba(23,25,28,.18))}
.ck-bubble{max-width:300px;background:#fff;border:1px solid var(--line);border-radius:14px 14px 14px 4px;
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
    face.className = 'ck-face ' + state;
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

  // 화면 아래를 천천히 오간다. 사람 손이 가는 오른쪽 아래를 계속 막지 않도록
  // 위치를 조금씩 바꾼다.
  var spots = [0.06, 0.3, 0.55, 0.74];
  var index = 0;
  function stroll(){
    var width = Math.max(window.innerWidth - buddy.offsetWidth - 24, 0);
    index = (index + 1) % spots.length;
    buddy.style.transform = 'translateX(' + Math.round(width * spots[index]) + 'px)';
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
        f'<div class="ck-face idle" style="--size:64px">{FACE_MARKUP}</div>'
        '<div class="ck-bubble"><button class="ck-close" title="닫기">×</button>'
        '<span class="ck-text">계약서를 올려주시면 조항을 훑어볼게요.</span></div>'
        "</div>"
    )


def brand_markup(size: int = 34) -> str:
    """사이드바 로고 자리에 들어가는 작은 체키."""
    return f'<div class="ck"><div class="ck-face idle" style="--size:{size}px">{FACE_MARKUP}</div></div>'
