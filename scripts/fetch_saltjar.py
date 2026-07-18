# -*- coding: utf-8 -*-
"""
생활성서사 유튜브 채널(공개 RSS 피드)에서 '듣는 소금항아리' 최신 영상을
찾아 data/saltjar.json 으로 저장한다.

RSS 피드는 API 키 없이 접근 가능한 유튜브 공식 공개 피드이며,
채널당 최근 업로드 15개까지 최신순으로 내려온다.

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests

CHANNEL_ID = "UCYqj-Z1LhisC9nAXMv-ZBWw"  # 생활성서사
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
TITLE_FILTER = "소금항아리"  # 채널에 다른 콘텐츠도 섞여 올라오므로 제목으로 필터링

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "saltjar.json"

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

    picked = None
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
        picked = {
            "videoId": video_id,
            "title": title.strip(),
            "published": published,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }
        break  # 피드는 최신순 정렬 → 첫 매치가 최신 소금항아리 영상

    if picked is None:
        print("no matching '소금항아리' entry found in feed", file=sys.stderr)
        sys.exit(1)

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "channelId": CHANNEL_ID,
        "channelUrl": f"https://www.youtube.com/channel/{CHANNEL_ID}",
        **picked,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved -> {OUT}: {picked['title']}")


if __name__ == "__main__":
    main()
