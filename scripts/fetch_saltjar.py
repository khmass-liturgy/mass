# -*- coding: utf-8 -*-
"""
생활성서사 유튜브 채널(공개 RSS 피드)에서 '듣는 소금항아리' 매일미사 영상을
날짜별로 모아 data/saltjar.json 으로 저장한다.

RSS 피드는 API 키 없이 접근 가능한 유튜브 공식 공개 피드이며,
채널당 최근 업로드 15개까지 최신순으로 내려온다.
이 채널에는 매일미사 영상 말고도 월간지 홍보 쇼츠가 '#소금항아리' 해시태그를
달고 섞여 올라오므로, 제목의 '[YYYY년 M월D일(요일) ...]' 날짜 표기를
필수 조건으로 삼아 매일미사 영상만 걸러낸다.

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

CHANNEL_ID = "UCYqj-Z1LhisC9nAXMv-ZBWw"  # 생활성서사
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
TITLE_FILTER = "소금항아리"  # 채널에 다른 콘텐츠도 섞여 올라오므로 제목으로 1차 필터링
MAX_ITEMS = 10

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

# 매일미사 영상 제목: '생활성서 듣는 #소금항아리 [2026년 8월20일(목) 성 비오 ...](...)'
# 쇼츠/홍보 영상에는 이 날짜 브래킷이 없으므로 이것이 곧 쇼츠 배제 조건이 된다.
MASS_DATE_RE = re.compile(r"\[\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*([^\]]*)\]")


def parse_mass_entry(title: str):
    """제목에서 매일미사 날짜와 전례일 표기를 뽑아 (date_str, label)로 반환한다.
    날짜 브래킷이 없으면(= 쇼츠·홍보 영상) None을 반환한다.
    """
    m = MASS_DATE_RE.search(title)
    if not m:
        return None
    y, mo, da, rest = m.groups()
    try:
        date_str = f"{int(y):04d}-{int(mo):02d}-{int(da):02d}"
    except ValueError:
        return None
    label = f"{int(y)}년 {int(mo)}월 {int(da)}일{rest.rstrip()}"
    return date_str, label


def main():
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

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
        parsed = parse_mass_entry(title)
        if parsed is None:
            print(f"skip (매일미사 날짜 없음 · 쇼츠 추정): {title.strip()}", file=sys.stderr)
            continue
        date_str, label = parsed
        video_id_el = entry.find("yt:videoId", NS)
        video_id = video_id_el.text if video_id_el is not None else None
        if not video_id:
            continue
        published_el = entry.find("atom:published", NS)
        published = published_el.text if published_el is not None else ""
        videos.append({
            "videoId": video_id,
            "date": date_str,
            "label": label,
            "title": title.strip(),
            "published": published,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
        if len(videos) >= MAX_ITEMS:
            break

    if not videos:
        print("no matching '소금항아리' 매일미사 entry found in feed", file=sys.stderr)
        sys.exit(1)

    videos.sort(key=lambda v: (v["date"], v["published"]), reverse=True)

    # 1순위: 오늘 날짜 영상 → 2순위: 오늘 이전 중 가장 최근 → 3순위: 목록의 최신
    picked = next((v for v in videos if v["date"] == today), None)
    if picked is None:
        picked = next((v for v in videos if v["date"] < today), None)
    if picked is None:
        picked = videos[0]

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "channelId": CHANNEL_ID,
        "channelUrl": f"https://www.youtube.com/channel/{CHANNEL_ID}",
        "videoId": picked["videoId"],
        "date": picked["date"],
        "label": picked["label"],
        "title": picked["title"],
        "published": picked["published"],
        "url": picked["url"],
        "count": len(videos),
        "videos": videos,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(videos)} videos -> {OUT} (오늘 {today} → {picked['date']}: {picked['label']})")


if __name__ == "__main__":
    main()
