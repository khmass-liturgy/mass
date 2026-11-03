# -*- coding: utf-8 -*-
"""
'오늘의 한 장' 성경 본문을 주교회의 성경(bible.cbck.or.kr/Knb)에서 받아
data/bible_today.json 으로 저장한다. bible_read.html 이 이 본문을 보여 주고
기기의 음성(TTS)으로 읽어 준다.

날짜 → 장 계산은 index.html 성경 카드와 같다: 2026-11-02(KST)이 창세기 1장이고
하루 한 장씩 요한 묵시록 22장까지 간 뒤 다시 처음으로 돈다.
지난 7일(다시 읽기)·오늘·내일(미리 읽기, 자정이 지나면 바로 오늘 장) 아홉 장을 받는다.
2026-11-02 이전 날짜는 없으므로 처음 며칠은 그보다 적다.

장 화면 구조 (서버에서 그려 내려오는 HTML)
------------------------------------------
  <div id="bibleContents" ...>
    <h3><p>천지 창조<sup class="annotation">1)</sup></p></h3>      ← 소제목
    <span class="highlight">1</span> ...
    <div class="text-justify"><p>한처음에 ...<sup ...>2)</sup></p></div>  ← 절
  ...
  <!-- 성경 Menu -->

읽어주기 음성 (--audio)
-----------------------
기기에 음성 합성(TTS)이 없는 폰(일부 앱 안 브라우저 등)을 위해, 장마다 mp3 를 미리 만든다.
edge-tts 한국어 음성(3일마다 현수·선희·인준 차례로)으로 장 제목·소제목·절을 하나씩 합성해 이어 붙이고, 각 부분이
시작하는 시각(marks)을 함께 적어 둔다 — 화면이 읽는 절을 따라가고, 절을 누르면 그리로 간다.
edge-tts 출력은 고정 48kbps(CBR) mp3 라 바이트 수로 길이를 바로 계산한다.
mp3 는 main 을 키우지 않도록 'bible-audio' 브랜치에 받은 날짜의 파일만 커밋 하나로
덮어써 올리고(워크플로), jsDelivr(커밋 고정 주소, audio/mpeg)로 재생한다.
이미 만든 날의 음성은 지난 JSON 의 주소에서 내려받아 다시 쓰고, 못 받으면 새로 만든다.
GitHub Release 파일은 늘 application/octet-stream 으로 내려와 아이폰에서 못 틀 수 있어 쓰지 않는다.
"""

import asyncio
import html
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = "https://bible.cbck.or.kr/Knb"
KST = ZoneInfo("Asia/Seoul")
EPOCH = date(2026, 11, 2)
OUT = Path(__file__).resolve().parent.parent / "data" / "bible_today.json"
AUDIO_DIR = Path(__file__).resolve().parent.parent / "build" / "bible_audio"
# 한국어 음성 셋을 3일마다 돌아가며 쓴다 (2026-11-02부터 현수 → 선희 → 인준 → 현수 …).
VOICES = [("ko-KR-HyunsuMultilingualNeural", "현수"), ("ko-KR-SunHiNeural", "선희"), ("ko-KR-InJoonNeural", "인준")]
VOICE_DAYS = 3


def voice_for(d: date):
    return VOICES[(d - EPOCH).days // VOICE_DAYS % len(VOICES)]
BYTES_PER_SEC = 48000 / 8   # edge-tts 기본 출력: audio-24khz-48kbitrate-mono-mp3
# JSON 의 audio 형식 표시. 음성 만드는 방식(목소리·저장 위치 등)을 바꾸면 올린다.
AUDIO_VER = 5
PAST_DAYS = 7   # 다시 읽을 수 있게 남겨 두는 지난 날 수

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# bible.cbck.or.kr/Knb 목차 그대로 (구약 46권, 신약 27권, 1328장)
BOOKS = [["Gn","창세기",50],["Ex","탈출기",40],["Lv","레위기",27],["Nm","민수기",36],["Dt","신명기",34],["Jos","여호수아기",24],["Jgs","판관기",21],["Ru","룻기",4],["1Sm","사무엘기 상권",31],["2Sm","사무엘기 하권",24],["1Kgs","열왕기 상권",22],["2Kgs","열왕기 하권",25],["1Chr","역대기 상권",29],["2Chr","역대기 하권",36],["Ezr","에즈라기",10],["Neh","느헤미야기",13],["Tb","토빗기",14],["Jdt","유딧기",16],["Est","에스테르기",10],["1Mc","마카베오기 상권",16],["2Mc","마카베오기 하권",15],["Jb","욥기",42],["Ps","시편",150],["Prv","잠언",31],["Eccl","코헬렛",12],["Sng","아가",8],["Wis","지혜서",19],["Sir","집회서",51],["Is","이사야서",66],["Jer","예레미야서",52],["Lam","애가",5],["Bar","바룩서",6],["Ez","에제키엘서",48],["Dn","다니엘서",14],["Hos","호세아서",14],["Jl","요엘서",4],["Am","아모스서",9],["Ob","오바드야서",1],["Jon","요나서",4],["Mi","미카서",7],["Na","나훔서",3],["Hb","하바쿡서",3],["Zep","스바니야서",3],["Hg","하까이서",2],["Zec","즈카르야서",14],["Mal","말라키서",3],["Mt","마태오 복음서",28],["Mk","마르코 복음서",16],["Lk","루카 복음서",24],["Jn","요한 복음서",21],["Acts","사도행전",28],["Rom","로마 신자들에게 보낸 서간",16],["1Cor","코린토 신자들에게 보낸 첫째 서간",16],["2Cor","코린토 신자들에게 보낸 둘째 서간",13],["Gal","갈라티아 신자들에게 보낸 서간",6],["Eph","에페소 신자들에게 보낸 서간",6],["Phil","필리피 신자들에게 보낸 서간",4],["Col","콜로새 신자들에게 보낸 서간",4],["1Thes","테살로니카 신자들에게 보낸 첫째 서간",5],["2Thes","테살로니카 신자들에게 보낸 둘째 서간",3],["1Tm","티모테오에게 보낸 첫째 서간",6],["2Tm","티모테오에게 보낸 둘째 서간",4],["Ti","티토에게 보낸 서간",3],["Phlm","필레몬에게 보낸 서간",1],["Heb","히브리인들에게 보낸 서간",13],["Jas","야고보 서간",5],["1Pt","베드로의 첫째 서간",5],["2Pt","베드로의 둘째 서간",3],["1Jn","요한의 첫째 서간",5],["2Jn","요한의 둘째 서간",1],["3Jn","요한의 셋째 서간",1],["Jude","유다 서간",1],["Rv","요한 묵시록",22]]
OT = 46
TOTAL = sum(b[2] for b in BOOKS)

CONTENTS_RE = re.compile(r'<div id="bibleContents"[^>]*>(.*?)<!-- 성경 Menu -->', re.S)
# 소제목(h3) 또는 절(번호 + 본문)을 나온 차례대로 읽는다.
PART_RE = re.compile(
    r'<h3>(.*?)</h3>'
    r'|<span class="highlight">\s*([^<]+?)\s*</span>.*?<div class="text-justify">(.*?)</div>',
    re.S)


def chapter_for(d: date):
    n = (d - EPOCH).days % TOTAL
    seq = n + 1
    for i, (code, name, count) in enumerate(BOOKS):
        if n < count:
            return {"code": code, "book": name, "chapter": n + 1, "seq": seq,
                    "testament": "구약" if i < OT else "신약"}
        n -= count
    raise AssertionError("unreachable")


def clean(raw_html: str) -> str:
    """각주 번호(<sup>)를 빼고 태그를 걷어낸다. 시편 등의 행 바꿈(<br>)은 \\n 으로 남긴다."""
    text = re.sub(r'<sup[^>]*>.*?</sup>', '', raw_html, flags=re.S)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', ln).strip() for ln in text.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def fetch_chapter(d: date) -> dict:
    ch = chapter_for(d)
    url = f"{BASE}/{ch['code']}/{ch['chapter']}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    m = CONTENTS_RE.search(r.text)
    if not m:
        raise ValueError(f"{url}: 본문 영역을 찾지 못했습니다.")
    items = []
    for head, num, body in PART_RE.findall(m.group(1)):
        if head:
            t = clean(head)
            if t:
                items.append({"h": t})
        else:
            t = clean(body)
            if t:
                items.append({"v": num.strip(), "t": t})
    if not any("v" in it for it in items):
        raise ValueError(f"{url}: 절을 하나도 읽지 못했습니다.")
    return {"date": d.isoformat(), **ch, "total": TOTAL, "url": url, "items": items}


def say_text(t: str) -> str:
    """bible_read.html 의 sayText 와 같다: 시편 번호 '(22)'·대괄호·행 바꿈 정리."""
    t = re.sub(r'^\(\d+\)\s*', '', t)
    return re.sub(r'[\[\]]', '', t).replace('\n', ' ').strip()


def sino(n: int) -> str:
    """장 번호를 한자어 수사로 (1 → 일, 23 → 이십삼, 150 → 백오십).
    숫자 그대로 두면 음성이 '1장'을 '한 장'으로 읽는다."""
    d = "영일이삼사오육칠팔구"
    out = ""
    for unit, place in ((100, "백"), (10, "십")):
        q, n = divmod(n, unit)
        if q:
            out += ("" if q == 1 else d[q]) + place
    return out + (d[n] if n else "")


def speech_parts(day: dict) -> list:
    """읽는 차례 — bible_read.html 의 parts 와 같은 순서(장 제목, 소제목·절)."""
    parts = [f"{day['book']} {sino(day['chapter'])}장"]
    for it in day["items"]:
        parts.append(it["h"] if "h" in it else say_text(it["t"]))
    return parts


async def synth(text: str, voice: str) -> bytes:
    import edge_tts
    for attempt in range(3):
        try:
            data = b""
            async for ch in edge_tts.Communicate(text, voice).stream():
                if ch["type"] == "audio":
                    data += ch["data"]
            if data:
                return data
        except Exception as e:
            print("  tts retry:", e, file=sys.stderr)
        await asyncio.sleep(2 + attempt * 3)
    raise RuntimeError(f"TTS 실패: {text[:30]}")


async def build_audio(day: dict) -> dict:
    voice, name = voice_for(date.fromisoformat(day["date"]))
    out, marks = b"", []
    for text in speech_parts(day):
        marks.append(round(len(out) / BYTES_PER_SEC, 2))
        out += await synth(text, voice)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIO_DIR / f"{day['date']}.mp3").write_bytes(out)
    # url 은 워크플로가 bible-audio 브랜치에 올린 뒤 그 커밋으로 채운다.
    return {"ver": AUDIO_VER, "file": f"{day['date']}.mp3", "voice": voice, "voice_name": name,
            "duration": round(len(out) / BYTES_PER_SEC, 1), "marks": marks}


def reuse_audio(old: dict | None, day: dict) -> dict | None:
    """지난번에 만든 같은 장의 음성을 그 주소에서 내려받아 다시 쓴다. 못 쓰면 None."""
    a = (old or {}).get("audio")
    voice, name = voice_for(date.fromisoformat(day["date"]))
    if not a or a.get("ver") != AUDIO_VER or not a.get("url") or old.get("code") != day["code"] \
            or old.get("chapter") != day["chapter"] or old.get("items") != day["items"] \
            or a.get("voice", VOICES[0][0]) != voice:   # 목소리를 적기 전 파일은 모두 현수
        return None
    try:
        r = requests.get(a["url"], timeout=60)
        r.raise_for_status()
        if abs(len(r.content) / BYTES_PER_SEC - a["duration"]) > 1:
            return None
    except Exception as e:
        print("  audio reuse failed:", day["date"], e, file=sys.stderr)
        return None
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIO_DIR / a["file"]).write_bytes(r.content)
    a = {k: v for k, v in a.items() if k != "url"}   # url 은 워크플로가 새 커밋으로 채운다
    a.update(voice=voice, voice_name=name)
    return a


def main() -> int:
    want_audio = "--audio" in sys.argv
    today = datetime.now(KST).date()
    try:
        old = {d["date"]: d for d in json.loads(OUT.read_text(encoding="utf-8")).get("days", [])}
    except Exception:
        old = {}

    days = []
    for k in range(-PAST_DAYS, 2):
        d = today + timedelta(days=k)
        if d < EPOCH:
            continue
        try:
            days.append(fetch_chapter(d))
        except Exception as e:
            print("bible chapter fetch/parse failed:", d, e, file=sys.stderr)
            if k >= 0:
                return 1          # 오늘·내일은 꼭 있어야 한다
            if d.isoformat() in old:
                days.append({x: v for x, v in old[d.isoformat()].items() if x != "audio"})

    if want_audio:
        # 'bible-audio' 브랜치를 이번 파일들로 통째로 덮어쓰므로(워크플로), 날마다 모든 날의
        # mp3 가 build/bible_audio 에 있어야 한다 — 지난번 것을 내려받거나 새로 만든다.
        for day in days:
            try:
                day["audio"] = reuse_audio(old.get(day["date"]), day) or asyncio.run(build_audio(day))
                print("  audio:", day["date"], day["audio"]["duration"], "s")
            except Exception as e:
                print("bible audio failed:", e, file=sys.stderr)   # 음성 없이도 본문은 저장한다

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": BASE,
        "days": days,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print("saved:", OUT)
    for d in days:
        print(" ", d["date"], d["book"], d["chapter"], "장,", sum("v" in it for it in d["items"]), "절")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
