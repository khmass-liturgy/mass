# -*- coding: utf-8 -*-
"""
룩스챔버콰이어(@luxchamberchoir7964) 유튜브 채널의 가톨릭 성가 영상을 모아
data/meditation_music.json 으로 저장한다 ('오늘의 묵상성가' 카드용).

영상마다 어느 시기(대림·성탄·사순·부활·성모성월·성심성월·순교자성월·로사리오성월·위령성월)에
어울리는지 seasons 를 붙여 둔다. 화면(index.html)은 지금 시기에 맞는 영상을
먼저 보여 주고, 해당하는 영상이 없으면 시기를 타지 않는 영상(general)을 보여 준다.

시기 분류는 영상 제목의 성가 번호로 한다(classify). 새로 올라온 영상이 어느 시기에도
안 걸리면 general 이 된다.

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

HANDLE_URL = "https://www.youtube.com/@luxchamberchoir7964/videos"
# (주소, 이 목록의 영상에 일괄로 붙일 시기 — 하나 또는 목록). 시기가 None 이면 성가집의 전례별 분류로 정한다.
# 같은 채널의 모음 재생목록은 채널 '동영상' 탭에 없는 영상이 있어 따로 읽고, 재생목록
# 이름이 곧 시기라서 그 시기로 확정한다.
SOURCES = [
    (HANDLE_URL, None),
    ("https://www.youtube.com/@candido_vocale/videos", None),   # 칸디도 보칼레 — 제목에 시기가 적혀 있다
    ("https://www.youtube.com/playlist?list=PLN9m430-p-ezAEEL1ORONtBtalaY3Pzk_", "souls"),     # 위령성가
    ("https://www.youtube.com/playlist?list=PLN9m430-p-ewyB8Tj020Hbz1jpOD_ghEz", "general"),   # 연중시기
    ("https://www.youtube.com/playlist?list=PLN9m430-p-ewtvJ5j9uxdv5OT1c1PkcAz", "christmas"), # 성탄시기
    ("https://www.youtube.com/playlist?list=PLN9m430-p-ezvhmCClAp_oovuqkecojG-", "advent"),    # 대림시기
    ("https://www.youtube.com/playlist?list=PLN9m430-p-ezTvBM1q1Vq9vIE0WdMTWrt", "easter"),    # 부활시기
    ("https://www.youtube.com/playlist?list=PLN9m430-p-ewSuNztPB8Hf6229cxsktSp", "marian"),    # 성모시기
    ("https://www.youtube.com/playlist?list=PLN9m430-p-ew2U8hhkwCURqnJqj7CHJSx", "lent"),      # 사순시기
    ("https://www.youtube.com/playlist?list=PLN9m430-p-exQAOWaaaVDzlZlhzACm0W6", ["eucharist", "general"]),  # 성체성가
]

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "meditation_music.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Cookie": "CONSENT=YES+1; SOCS=CAI",
}
INITIAL_DATA_RE = re.compile(r"var ytInitialData = (\{.*?\});</script>", re.S)
HYMN_NO_RE = re.compile(r"가톨릭\s*성가\s*(\d+)\s*번")
MAX_PAGES = 20

def fetch_all_videos() -> tuple:
    """(영상 id → 제목, 영상 id → 확정된 시기) 를 돌려준다."""
    videos, forced = {}, {}
    for url, season in SOURCES:
        for vid, title in fetch_videos(url).items():
            videos.setdefault(vid, title)
            if season:
                forced[vid] = season
    return videos, forced


# 채널 밖에서 직접 고른 영상. 매번 목록 끝에 붙인다.
MANUAL_ITEMS = [
    {"videoId": "Tpwp1OZEoZY", "title": "가톨릭 묵상 성가", "seasons": ["general"]},
]


def walk(node, videos, tokens):
    if isinstance(node, dict):
        lv = node.get("lockupViewModel")
        if isinstance(lv, dict) and lv.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
            title = (lv.get("metadata", {}).get("lockupMetadataViewModel", {})
                       .get("title", {}).get("content", "")).strip()
            if lv.get("contentId") and title and "보너스" not in title:
                videos.setdefault(lv["contentId"], title)
        item = node.get("continuationItemRenderer")
        if isinstance(item, dict):
            tok = (item.get("continuationEndpoint", {}).get("continuationCommand", {})
                       .get("token"))
            if tok:
                tokens.append(tok)
        for v in node.values():
            walk(v, videos, tokens)
    elif isinstance(node, list):
        for v in node:
            walk(v, videos, tokens)


def fetch_videos(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    m = INITIAL_DATA_RE.search(r.text)
    if not m:
        raise ValueError("ytInitialData 를 찾지 못함")
    key = re.search(r'"INNERTUBE_API_KEY":"([\w-]+)"', r.text).group(1)
    ver = re.search(r'"clientVersion":"([\d.]+)"', r.text).group(1)
    videos, tokens = {}, []
    walk(json.loads(m.group(1)), videos, tokens)
    for _ in range(MAX_PAGES):
        if not tokens:
            break
        body = {"context": {"client": {"clientName": "WEB", "clientVersion": ver,
                                       "hl": "ko", "gl": "KR"}},
                "continuation": tokens.pop(0)}
        tokens.clear()
        rr = requests.post(f"https://www.youtube.com/youtubei/v1/browse?key={key}",
                           json=body, headers=HEADERS, timeout=30)
        rr.raise_for_status()
        walk(rr.json(), videos, tokens)
    return videos


# 성가집 자체가 곡마다 '전례별' 분류(연중·대림·성탄·사순·부활·성모·성인·성체·성심)를 갖고 있다.
# 굿뉴스 성가 검색 페이지에 나와 있으므로, 성가 번호로 그 분류를 읽어 와 시기로 옮긴다.
HYMN_PAGE = "https://maria.catholic.or.kr/sungga/search/sungga_view.asp?ctxtIndex={}"
LITURGY_RE = re.compile(r'전례별</th>\s*<td class="al">(.*?)</td>', re.S)
SEASON_BY_CATEGORY = {
    "대림": "advent", "성탄": "christmas", "사순": "lent", "부활": "easter",
    "성모": "marian", "성심": "sacredheart", "위령": "souls",
}
# 분류만으로는 못 정하는 곡을 직접 적는다. 성가 번호 → 시기 목록.
SEASON_OVERRIDES = {
    271: ["rosary", "marian"],   # 로사리오 기도 드릴 때 — 10월 묵주기도성월
    255: ["easter", "marian"],   # 하늘의 여왕 — 부활 시기에 바치는 성모 찬송
}


def hymn_category(no: int):
    try:
        r = requests.get(HYMN_PAGE.format(no), headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.encoding = r.apparent_encoding
        m = LITURGY_RE.search(r.text)
        return m.group(1).strip() if m else None
    except requests.RequestException:
        return None


def classify(title: str) -> list:
    """영상 제목으로 어울리는 시기 목록을 돌려준다. 어디에도 안 걸리면 ['general']."""
    if "성모성월" in title:
        return ["marianmonth"]   # 5월 성모성월에만 쓴다. 10월 등 그냥 성모 주제 달에는 안 나온다.
    m = HYMN_NO_RE.search(title)
    if not m:
        return ["general"]
    no = int(m.group(1))
    if no in SEASON_OVERRIDES:
        return SEASON_OVERRIDES[no]
    cat = hymn_category(no)
    if cat == "성인":
        return ["martyrs"] if "순교" in title else ["general"]
    return [SEASON_BY_CATEGORY.get(cat, "general")]


def seasons_for(vid: str, title: str, forced: dict) -> list:
    """직접 적어 둔 예외(SEASON_OVERRIDES) → 재생목록이 정한 시기 → 성가집 분류 순서로 정한다."""
    m = HYMN_NO_RE.search(title)
    if m and int(m.group(1)) in SEASON_OVERRIDES:
        return SEASON_OVERRIDES[int(m.group(1))]
    if vid in forced:
        f = forced[vid]
        return list(f) if isinstance(f, list) else [f]
    return classify(title)


def main() -> int:
    try:
        videos, forced = fetch_all_videos()
        if not videos:
            raise ValueError("영상을 하나도 찾지 못했습니다.")
    except Exception as e:
        print("meditation_music fetch failed:", e, file=sys.stderr)
        return 1

    items = [{"videoId": vid, "title": title,
              "seasons": seasons_for(vid, title, forced)}
             for vid, title in videos.items()]
    items += [m for m in MANUAL_ITEMS if m["videoId"] not in videos]
    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": HANDLE_URL,
        "count": len(items),
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("saved:", OUT, f"({len(items)}편)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
