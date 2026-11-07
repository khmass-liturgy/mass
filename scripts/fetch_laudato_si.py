# -*- coding: utf-8 -*-
"""
'찬미받으소서' 카드·화면(laudato_si.html)에 보여 줄 오늘의 유튜브 영상을 고른다.

찬미받으소서 회칙과 이어지는 주제 22가지(기후위기, 빙하 감소, 쓰레기 줄이기 …
생태적 회개, 기후 난민, 미래 세대)를 하루에 하나씩 돌려 가며,
그날 주제로 유튜브를 검색해 영상 한 편(+ 더 볼 영상 몇 편)을 골라
data/laudato_si.json 으로 저장한다.

- 주제 순서는 화면(laudato_si.html, index.html)과 같다: 1970-01-01 부터 센 날수 % 주제 수(22) (한국 날짜).
- 가톨릭 채널·제목의 영상을 앞세우고, 한글 제목·1~40분 길이만 남긴다.
- 최근 60일 안에 보여 준 영상은 다시 고르지 않는다(history).
- 고른 영상이 한국에서 재생되고 다른 사이트에 넣어 재생(임베드)할 수 있는지 확인한다.
- 주제마다 마지막으로 고른 영상을 byTopic 에 남겨, 갱신이 하루 밀려도 화면이 그날 주제의 영상을 보여 줄 수 있게 한다.

GitHub Actions에서 매일 실행됨.
"""

import json
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "laudato_si.json"

# (주제, 검색어 목록 — 앞의 것부터 찾고, 쓸 만한 영상이 모자라면 다음 검색어로)
TOPICS = [
    ("지구온난화와 기후위기", ["찬미받으소서 기후위기 가톨릭", "기후위기 천주교 생태"]),
    ("녹아내리는 빙하", ["빙하 기후위기 가톨릭 생태", "빙하 감소 기후변화"]),
    ("쓰레기 줄이기", ["쓰레기 줄이기 가톨릭 생태 실천", "제로웨이스트 천주교"]),
    ("소비 절제 — 과소비 줄이기", ["소비 절제 찬미받으소서", "과소비 가톨릭 생태 영성"]),
    ("탐욕에서의 자유", ["탐욕 프란치스코 교황 찬미받으소서", "탐욕에서 자유 가톨릭 강론"]),
    ("우리 공동의 집, 지구 살리기", ["우리 공동의 집 찬미받으소서", "공동의 집 지구 가톨릭"]),
    ("탄소 배출 줄이기", ["탄소중립 가톨릭 생태", "탄소 배출 줄이기 천주교"]),
    ("일회용품 줄이기", ["일회용품 줄이기 가톨릭", "일회용품 천주교 생태 실천"]),
    ("자연 보호와 창조 질서 보전", ["창조질서 보전 가톨릭", "자연보호 천주교 생태"]),
    ("모든 생명은 소중합니다", ["생물다양성 찬미받으소서", "모든 피조물 소중 가톨릭 생태"]),
    ("가난한 이를 돌보는 형제애", ["가난한 이 프란치스코 교황 형제애", "가난한 이웃 돌봄 가톨릭"]),
    ("서로를 필요로 하는 우리", ["모든 것은 연결되어 있다 찬미받으소서", "통합생태론 찬미받으소서"]),
    ("삼위일체와 피조물의 관계", ["삼위일체 피조물 찬미받으소서", "삼위일체 창조 가톨릭 강의"]),
    ("창조주 하느님을 찬미함", ["창조주 하느님 찬미 가톨릭 강론", "창조 신앙 천주교"]),
    ("아시시의 성 프란치스코", ["아시시의 성 프란치스코 태양의 찬가", "성 프란치스코 가톨릭"]),
    ("모든 피조물의 모후와 성 요셉", ["모든 피조물의 모후 찬미받으소서", "성 요셉 찬미받으소서", "성 요셉 가톨릭 강론"]),
    ("물은 생명입니다", ["물 부족 찬미받으소서", "물 아끼기 가톨릭 생태"]),
    ("생태적 회개", ["생태적 회개 찬미받으소서", "생태적 회개 가톨릭 강의"]),
    ("음식 낭비 줄이기", ["음식물 쓰레기 줄이기 가톨릭", "음식 낭비 프란치스코 교황"]),
    ("기후 난민과 이웃", ["기후 난민 가톨릭", "기후난민 프란치스코 교황"]),
    ("미래 세대를 위한 정의", ["미래 세대 기후위기 가톨릭", "다음 세대 지구 찬미받으소서"]),
    ("주일의 쉼과 감사의 식탁", ["식사 전 감사 기도 가톨릭", "주일 거룩하게 지내기 가톨릭 강론"]),
]

HISTORY_DAYS = 60
MIN_SEC, MAX_SEC = 60, 40 * 60
MORE = 4

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Cookie": "CONSENT=YES+1; SOCS=CAI",
}
INITIAL_DATA_RE = re.compile(r"var ytInitialData = (\{.*?\});</script>", re.S)
HANGUL_RE = re.compile(r"[가-힣]")
CATHOLIC_RE = re.compile(r"가톨릭|천주교|cpbc|평화방송|CBCK|주교회의|교구|성당|신부|수녀|바오로딸|"
                         r"찬미받으소서|교황|Vatican|바티칸|생태환경|가톨릭기후행동|LSM", re.I)
COUNTRIES_RE = re.compile(r'"availableCountries":\[([^\]]*)\]')
STATUS_RE = re.compile(r'"playabilityStatus":\{"status":"([A-Z_]+)"')
EMBED_RE = re.compile(r'"playableInEmbed":(true|false)')


def topic_index(d: date) -> int:
    return (d - date(1970, 1, 1)).days % len(TOPICS)


def seconds(text):
    if not text:
        return None
    parts = text.split(":")
    if not all(p.isdigit() for p in parts):
        return None
    s = 0
    for p in parts:
        s = s * 60 + int(p)
    return s


def search(query: str) -> list:
    """유튜브 검색 결과(동영상만)를 [{videoId,title,channel,duration,published}] 로."""
    url = ("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
           + "&sp=EgIQAQ%253D%253D")
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    m = INITIAL_DATA_RE.search(r.text)
    if not m:
        raise ValueError("ytInitialData 없음: " + query)
    out = []

    def walk(n):
        if isinstance(n, dict):
            v = n.get("videoRenderer")
            if isinstance(v, dict) and v.get("videoId"):
                title = "".join(x.get("text", "") for x in v.get("title", {}).get("runs", []))
                out.append({
                    "videoId": v["videoId"],
                    "title": title.strip(),
                    "channel": (v.get("ownerText", {}).get("runs") or [{}])[0].get("text", ""),
                    "duration": seconds(v.get("lengthText", {}).get("simpleText")),
                    "published": v.get("publishedTimeText", {}).get("simpleText", ""),
                })
            for x in n.values():
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(json.loads(m.group(1)))
    return out


# 성가 연습·반주용 영상 등 주제와 상관없는 것은 뺀다
SKIP_RE = re.compile(r"파트\s*연습|반주|\bMR\b|노래방|악보|가사\s*연습|shorts", re.I)


def usable(v) -> bool:
    return (bool(HANGUL_RE.search(v["title"])) and not SKIP_RE.search(v["title"]) and v["duration"] is not None
            and MIN_SEC <= v["duration"] <= MAX_SEC)


def playable(video_id: str):
    """한국에서 재생되고 임베드할 수 있으면 True, 아니면 False, 확인 못 하면 None."""
    for wait in (0, 5, 15):
        time.sleep(wait)
        try:
            r = requests.get(f"https://www.youtube.com/watch?v={video_id}", headers=HEADERS, timeout=30)
        except requests.RequestException:
            continue
        if r.status_code == 404:
            return False
        if r.status_code != 200:
            continue
        e = EMBED_RE.search(r.text)
        if e and e.group(1) == "false":
            return False
        c = COUNTRIES_RE.search(r.text)
        if c and c.group(1).strip() and '"KR"' not in c.group(1):
            return False
        s = STATUS_RE.search(r.text)
        if s:
            return s.group(1) not in ("UNPLAYABLE", "ERROR")
        return None
    return None


def load_old() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    today = datetime.now(KST).date()
    if len(sys.argv) > 1:          # 시험용: python fetch_laudato_si.py 2026-11-08
        today = date.fromisoformat(sys.argv[1])
    idx = topic_index(today)
    topic, queries = TOPICS[idx]

    old = load_old()
    cutoff = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    history = [h for h in old.get("history", []) if cutoff <= h.get("date", "") < today.isoformat()]
    recent = {h["videoId"] for h in history}

    cands, seen = [], set()
    try:
        for q in queries:
            for v in search(q):
                if v["videoId"] in seen or not usable(v):
                    continue
                seen.add(v["videoId"])
                v["catholic"] = bool(CATHOLIC_RE.search(v["title"] + " " + v["channel"]))
                cands.append(v)
            if sum(1 for v in cands if v["catholic"] and v["videoId"] not in recent) >= MORE + 1:
                break
            time.sleep(1)
    except Exception as e:
        print("laudato si search failed:", e, file=sys.stderr)
        return 1

    # 가톨릭 영상 먼저, 그 안에서는 검색 순위 그대로. 최근에 보여 준 영상은 맨 뒤로.
    cands.sort(key=lambda v: (v["videoId"] in recent, not v["catholic"]))
    pick, rest = None, []
    for v in cands:
        if pick is None and v["videoId"] not in recent:
            ok = playable(v["videoId"])
            if ok is False:
                print("  재생·임베드 불가로 건너뜀:", v["videoId"], file=sys.stderr)
                continue
            pick = v
        elif len(rest) < MORE:
            rest.append(v)
    if pick is None and cands:      # 다 최근에 본 영상이면 그중 첫 번째라도
        pick = cands[0]
        rest = [v for v in cands[1:MORE + 1]]
    if pick is None:
        print("영상을 찾지 못함:", topic, file=sys.stderr)
        return 1

    def slim(v):
        return {k: v[k] for k in ("videoId", "title", "channel", "duration", "published")}

    history.append({"date": today.isoformat(), "videoId": pick["videoId"]})
    # 주제 이름으로 남긴다 — 주제를 더하거나 순서를 바꿔도 엉뚱한 주제의 영상이 붙지 않게
    titles = {t for t, _ in TOPICS}
    by_topic = {k: v for k, v in old.get("byTopic", {}).items() if k in titles}
    by_topic[topic] = {"date": today.isoformat(), "video": slim(pick), "more": [slim(v) for v in rest]}

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "date": today.isoformat(),
        "topicIndex": idx,
        "topic": topic,
        "query": queries[0],
        "video": slim(pick),
        "more": [slim(v) for v in rest],
        "topics": [{"title": t, "query": q[0]} for t, q in TOPICS],
        "byTopic": {t: by_topic[t] for t, _ in TOPICS if t in by_topic},
        "history": history,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"saved: {OUT.name} — {today} [{idx}] {topic}")
    print(f"  {pick['videoId']} {pick['title']} ({pick['channel']})")
    for v in rest:
        print(f"   + {v['videoId']} {v['title']} ({v['channel']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
