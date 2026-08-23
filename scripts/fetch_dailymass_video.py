# -*- coding: utf-8 -*-
"""
cpbc TV(가톨릭평화방송) '매일미사' 재생목록에서 날짜별 미사 영상을 모아
data/dailymass_video.json 으로 저장한다.

재생목록 제목 형식이 일정하다.
  '2026년 8월 24일 성 바르톨로메오 사도 축일 매일미사ㅣ설재 안셀모 신부 집전'
   └ 날짜 ──────┘ └ 전례일 ──────────┘        └ 집전 신부 ──┘
날짜 앞뒤에 'ㅣ' 가 끼거나 '연중 20주간'/'연중 제20주간' 처럼 표기가
흔들리는 경우가 있어, 날짜와 '매일미사' 를 기준으로 잘라 낸다.

수집은 재생목록 페이지 HTML 의 ytInitialData 를 파싱한다.
(유튜브 RSS 피드는 2026-08 현재 404 를 돌려주므로 쓰지 않는다.)

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PLAYLIST_ID = "PLpB9z9SOeZQfGRsNAtfExml1MP8zwjc0C"  # cpbc TV · 매일미사
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"
CHANNEL = "cpbc TV · 가톨릭평화방송"
MAX_ITEMS = 14

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "dailymass_video.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

YT_INITIAL_DATA_RE = re.compile(r"ytInitialData\s*=\s*(\{.*?\});</script>", re.S)
DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
TRIM = " ㅣ|·-—:,"


def parse_entry(title: str):
    """제목에서 (날짜, 전례일, 집전 신부)를 뽑는다. 형식이 안 맞으면 None."""
    m = DATE_RE.search(title)
    if not m:
        return None
    y, mo, da = m.groups()
    try:
        date_str = f"{int(y):04d}-{int(mo):02d}-{int(da):02d}"
    except ValueError:
        return None

    rest = title[m.end():]
    if "매일미사" in rest:
        before, after = rest.split("매일미사", 1)
    else:
        before, after = rest, ""

    liturgy = before.strip(TRIM)
    priest = after.strip(TRIM)
    # '설재 안셀모 신부 집전' → '설재 안셀모 신부'
    priest = re.sub(r"\s*집전\s*$", "", priest).strip(TRIM)
    return date_str, liturgy, priest


def walk_lockups(node, sink):
    """ytInitialData 트리에서 영상 카드(lockupViewModel)를 모은다."""
    if isinstance(node, dict):
        lv = node.get("lockupViewModel")
        if isinstance(lv, dict) and lv.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
            title = (lv.get("metadata", {})
                       .get("lockupMetadataViewModel", {})
                       .get("title", {})
                       .get("content"))
            vid = lv.get("contentId")
            if vid and title:
                sink.append((vid, title))
        for v in node.values():
            walk_lockups(v, sink)
    elif isinstance(node, list):
        for v in node:
            walk_lockups(v, sink)


def main():
    now = datetime.now(KST)

    try:
        r = requests.get(PLAYLIST_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        m = YT_INITIAL_DATA_RE.search(r.text)
        if not m:
            raise ValueError("ytInitialData 를 찾지 못했습니다 (페이지 구조 변경 가능성)")
        found = []
        walk_lockups(json.loads(m.group(1)), found)
    except Exception as e:
        print("재생목록 수집 실패:", e, file=sys.stderr)
        sys.exit(1)

    seen = set()
    videos = []
    for vid, title in found:
        if vid in seen:
            continue
        seen.add(vid)
        parsed = parse_entry(title)
        if parsed is None:
            print(f"skip (형식 불일치): {title}", file=sys.stderr)
            continue
        date_str, liturgy, priest = parsed
        videos.append({
            "videoId": vid,
            "date": date_str,
            "liturgy": liturgy,
            "priest": priest,
            "url": f"https://www.youtube.com/watch?v={vid}&list={PLAYLIST_ID}",
        })

    if not videos:
        print("매일미사 항목을 찾지 못했습니다", file=sys.stderr)
        sys.exit(1)

    videos.sort(key=lambda v: v["date"], reverse=True)
    videos = videos[:MAX_ITEMS]

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "channel": CHANNEL,
        "playlistId": PLAYLIST_ID,
        "playlistUrl": PLAYLIST_URL,
        "count": len(videos),
        "videos": videos,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(videos)} videos -> {OUT}: 최신 {videos[0]['date']} {videos[0]['liturgy']} / {videos[0]['priest']}")


if __name__ == "__main__":
    main()
