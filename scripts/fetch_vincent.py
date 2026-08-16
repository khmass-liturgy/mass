# -*- coding: utf-8 -*-
"""
'빈첸시오말씀방' 유튜브 채널(공개 RSS 피드)에서 매일 올라오는
[묵상] 영상을 날짜별로 모아 data/vincent.json 으로 저장한다.

RSS 피드는 API 키 없이 접근 가능한 유튜브 공식 공개 피드이며,
채널당 최근 업로드 15개까지 최신순으로 내려온다.
이 채널은 하루에 [묵상]/[독서,복음,묵상]/복음 말씀 영상을 각각 올리므로,
제목에 '[묵상]'이 포함된 영상만 걸러서 날짜별 목록을 만든다.

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
TITLE_FILTER = "[묵상]"  # 채널에 성경 구절/독서 영상도 섞여 올라오므로 제목으로 필터링
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

DATE_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(.*)")


def clean_title(title: str, published_kst_date: str):
    """제목에서 '[묵상] YYYY년 M월 D일 <설명> #태그...' 형태를 분리해
    (날짜, 짧은 설명) 튜플로 반환한다. 날짜를 못 찾으면 게시일을 대신 쓴다.
    """
    after_tag = title.split(TITLE_FILTER, 1)
    rest = after_tag[1].strip() if len(after_tag) > 1 else title
    m = DATE_RE.match(rest)
    if m:
        y, mo, da, desc = m.groups()
        date_str = f"{int(y):04d}-{int(mo):02d}-{int(da):02d}"
    else:
        date_str = published_kst_date
        desc = rest
    desc = desc.split(" #")[0].strip()
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
        title = title_el.text if title_el is not None and title_el.text else ""
        if TITLE_FILTER not in title:
            continue
        video_id_el = entry.find("yt:videoId", NS)
        video_id = video_id_el.text if video_id_el is not None else None
        if not video_id:
            continue
        published_el = entry.find("atom:published", NS)
        published = published_el.text if published_el is not None else ""
        try:
            published_kst = datetime.fromisoformat(published).astimezone(KST)
            published_kst_date = published_kst.strftime("%Y-%m-%d")
        except Exception:
            published_kst_date = now.strftime("%Y-%m-%d")

        date_str, desc = clean_title(title.strip(), published_kst_date)
        videos.append({
            "videoId": video_id,
            "date": date_str,
            "title": desc or title.strip(),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
        if len(videos) >= MAX_ITEMS:
            break

    if not videos:
        print("no matching '[묵상]' entries found in feed", file=sys.stderr)
        sys.exit(1)

    videos.sort(key=lambda v: (v["date"], v["videoId"]), reverse=True)

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
