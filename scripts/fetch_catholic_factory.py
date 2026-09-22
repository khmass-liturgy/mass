# -*- coding: utf-8 -*-
"""
유튜브 '미니다큐 가톨릭발전소' 재생목록에서 영상 제목·id를 모아
data/catholic_factory.json 으로 저장한다.

배경
----
이 채널은 순교자 성월(9월)·사순시기·대림시기에 맞춰 그 시기 전용
영상(제목에 '[순교자 성월]', '[사순시기 묵상]', '[대림시기 묵상]' 등으로
표시됨)을 올려 둔다. 화면(index.html)에서 카드 하나로 이 영상들을
보여 줄 때, 지금이 어느 전례 시기인지에 따라 그 시기에 맞는 영상을
우선 보여 주고 싶어서, 제목에 적힌 시기 표시로 미리 분류해 둔다.

분류는 여기서 하고, '그중 오늘은 어떤 영상을 보여 줄지'는 화면
(index.html) 쪽에서 한국 날짜를 기준으로 고른다 (가톨릭신문
기획특집·오늘의 떼제 음악 카드와 같은 방식).

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = "https://www.youtube.com"
PLAYLIST_ID = "PL3MR_mHrWxazXvh82RdqRF774UdygRE0q"
PLAYLIST_URL = f"{BASE}/playlist?list={PLAYLIST_ID}"

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "catholic_factory.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

INITIAL_DATA_RE = re.compile(r"var ytInitialData = (\{.*?\});</script>", re.S)

# 제목에 적힌 시기 표시로 분류한다. 예: '[순교자 성월 묵상] ...', '[사순시기 묵상] ...'
MARTYRS_RE = re.compile(r"순교자\s*성월")
LENT_RE = re.compile(r"사순\s*시기")
ADVENT_RE = re.compile(r"대림\s*시기")


def find_lockups(data, content_type: str) -> list:
    """ytInitialData 트리에서 원하는 종류(영상)의 lockupViewModel 을 모은다."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            lv = node.get("lockupViewModel")
            if isinstance(lv, dict) and lv.get("contentType") == content_type:
                out.append(lv)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return out


def classify(title: str) -> str:
    if MARTYRS_RE.search(title):
        return "martyrs"
    if LENT_RE.search(title):
        return "lent"
    if ADVENT_RE.search(title):
        return "advent"
    return "general"


def fetch_playlist() -> list:
    r = requests.get(PLAYLIST_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    m = INITIAL_DATA_RE.search(r.text)
    if not m:
        raise ValueError("ytInitialData를 찾지 못함")
    data = json.loads(m.group(1))

    items = []
    for lv in find_lockups(data, "LOCKUP_CONTENT_TYPE_VIDEO"):
        video_id = lv.get("contentId")
        title = lv.get("metadata", {}).get("lockupMetadataViewModel", {}) \
                   .get("title", {}).get("content", "").strip()
        if not video_id or not title:
            continue
        items.append({
            "title": title,
            "videoId": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "group": classify(title),
        })
    return items


def main() -> int:
    try:
        items = fetch_playlist()
        if not items:
            raise ValueError("영상을 하나도 찾지 못했습니다.")
    except Exception as e:
        print("catholic_factory fetch/parse failed:", e, file=sys.stderr)
        return 1

    groups = {"martyrs": [], "lent": [], "advent": [], "general": []}
    for it in items:
        groups[it["group"]].append({"title": it["title"], "videoId": it["videoId"], "url": it["url"]})

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": PLAYLIST_URL,
        "count": len(items),
        "groups": groups,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("saved:", OUT)
    for key in ("martyrs", "lent", "advent", "general"):
        print(f"  {key}: {len(groups[key])}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
