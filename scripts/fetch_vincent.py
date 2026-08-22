# -*- coding: utf-8 -*-
"""
'빈첸시오말씀방' 유튜브 채널(공개 RSS 피드)에서 매일미사 영상을
날짜별로 모아 data/vincent.json 으로 저장한다.

RSS 피드는 API 키 없이 접근 가능한 유튜브 공식 공개 피드이며,
채널당 최근 업로드 15개까지 최신순으로 내려온다.

이 채널은 같은 날짜로 여러 종류를 올린다.
  · '가톨릭 매일미사 [독서,복음,묵상] 2026년 8월 17일 …'  ← 전체 매일미사 (원하는 것)
  · '가톨릭 매일미사 [묵상] 2026년 8월 17일 …'            ← 묵상만 담은 쇼츠
  · '매일미사 마태오복음(19,16-22) …'                     ← 성경 구절 클립
제목의 대괄호에 '독서'와 '복음'이 함께 든 항목만 매일미사로 인정하고,
쇼츠(/shorts/ 링크)는 형식 자체로 배제한다.

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests

CHANNEL_ID = "UC-0yMi0sXeG2HYmKCzwM7sQ"  # 빈첸시오말씀방
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
MAX_ITEMS = 10

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "vincent.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*(.*)")

# 전체 매일미사 영상의 표식: 대괄호 안에 '독서'와 '복음'이 함께 들어 있다.
# 묵상만 담은 쇼츠('[묵상]')와 성경 구절 클립은 이 조건에서 걸러진다.
MASS_TAG_RE = re.compile(r"\[[^\]]*독서[^\]]*복음[^\]]*\]")


def parse_mass_entry(title: str):
    """전체 매일미사 제목에서 (날짜, 전례일 표기)를 뽑는다.

    예) '가톨릭 매일미사 [독서,복음,묵상] 2026년 8월 17일 연중 제20주간 월요일'
        → ('2026-08-17', '연중 제20주간 월요일')
    매일미사 표식이나 날짜가 없으면 None을 돌려 호출부에서 건너뛰게 한다.
    """
    m = MASS_TAG_RE.search(title)
    if not m:
        return None
    rest = title[m.end():].strip()
    d = DATE_RE.match(rest)
    if not d:
        return None
    y, mo, da, desc = d.groups()
    try:
        date_str = f"{int(y):04d}-{int(mo):02d}-{int(da):02d}"
    except ValueError:
        return None
    desc = desc.split("#")[0].strip(" ·-—")
    return date_str, desc


def main():
    now = datetime.now(KST)

    try:
        r = requests.get(FEED_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print("feed fetch/parse failed:", e, file=sys.stderr)
        sys.exit(1)

    entries = root.findall("atom:entry", NS)

    videos = []
    for entry in entries:
        title_el = entry.find("atom:title", NS)
        title = (title_el.text or "").strip() if title_el is not None else ""

        # 쇼츠는 링크 형식만으로 걸러낸다 (제목이 매일미사처럼 보여도 배제)
        link_el = entry.find("atom:link", NS)
        href = link_el.get("href", "") if link_el is not None else ""
        if "/shorts/" in href:
            print(f"skip (쇼츠): {title}", file=sys.stderr)
            continue

        parsed = parse_mass_entry(title)
        if parsed is None:
            print(f"skip (매일미사 아님): {title}", file=sys.stderr)
            continue
        date_str, desc = parsed

        video_id_el = entry.find("yt:videoId", NS)
        video_id = video_id_el.text if video_id_el is not None else None
        if not video_id:
            continue
        published_el = entry.find("atom:published", NS)
        published = published_el.text if published_el is not None else ""

        videos.append({
            "videoId": video_id,
            "date": date_str,
            "title": desc or title,
            "published": published,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
        if len(videos) >= MAX_ITEMS:
            break

    if not videos:
        print("no 매일미사([독서,복음,묵상]) entry found in feed", file=sys.stderr)
        sys.exit(1)

    videos.sort(key=lambda v: (v["date"], v["published"]), reverse=True)

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "channelId": CHANNEL_ID,
        "channelUrl": f"https://www.youtube.com/channel/{CHANNEL_ID}",
        "count": len(videos),
        "videos": videos,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(videos)} videos -> {OUT}")


if __name__ == "__main__":
    main()
