# -*- coding: utf-8 -*-
"""
'빈첸시오말씀방' 유튜브 채널에서 매일미사 영상을 날짜별로 모아
data/vincent.json 으로 저장한다.

수집 경로
---------
1순위: 채널 '/videos' 탭 HTML 에 들어 있는 ytInitialData 파싱
       - 쇼츠는 별도 탭이라 이 목록에 애초에 섞이지 않는다.
2순위: 공개 RSS 피드 (youtube.com/feeds/videos.xml)
       - 2026-08-22 현재 이 채널·생활성서사 채널 모두 404 를 돌려주지만,
         유튜브가 되살릴 경우를 대비해 예비 경로로 남겨 둔다.
       - RSS 로 받을 때는 /shorts/ 링크를 형식으로 배제한다.

이 채널은 같은 날짜로 여러 종류를 올린다.
  · '가톨릭 매일미사 [독서,복음,묵상] 2026년 8월 22일 …'  ← 전체 매일미사 (원하는 것)
  · '가톨릭 매일미사 [묵상] 2026년 8월 22일 …'            ← 묵상만 담은 쇼츠
  · '매일미사 마태오복음(19,16-22) …'                     ← 성경 구절 클립
따라서 어느 경로로 받든 제목의 대괄호에 '독서'와 '복음'이 함께 든
항목만 매일미사로 인정한다.

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
VIDEOS_URL = f"https://www.youtube.com/channel/{CHANNEL_ID}/videos"
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

YT_INITIAL_DATA_RE = re.compile(r"ytInitialData\s*=\s*(\{.*?\});</script>", re.S)


def parse_mass_entry(title: str):
    """전체 매일미사 제목에서 (날짜, 전례일 표기)를 뽑는다.

    예) '가톨릭 매일미사 [독서,복음,묵상] 2026년 8월 22일 복되신 동정 마리아 모후 기념일'
        → ('2026-08-22', '복되신 동정 마리아 모후 기념일')
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


def _walk_lockups(node, sink):
    """ytInitialData 트리를 훑어 영상 카드(lockupViewModel)를 모은다."""
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
            _walk_lockups(v, sink)
    elif isinstance(node, list):
        for v in node:
            _walk_lockups(v, sink)


def entries_from_channel_page():
    """채널 '/videos' 탭에서 (videoId, title) 목록을 뽑는다. 쇼츠는 이 탭에 없다."""
    r = requests.get(VIDEOS_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    m = YT_INITIAL_DATA_RE.search(r.text)
    if not m:
        raise ValueError("ytInitialData 를 찾지 못했습니다 (페이지 구조 변경 가능성)")
    found = []
    _walk_lockups(json.loads(m.group(1)), found)
    seen = set()
    uniq = []
    for vid, title in found:
        if vid not in seen:
            seen.add(vid)
            uniq.append((vid, title))
    return uniq


def entries_from_feed():
    """예비 경로: 공개 RSS 피드. 쇼츠는 링크 형식으로 배제한다."""
    r = requests.get(FEED_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for entry in root.findall("atom:entry", NS):
        link_el = entry.find("atom:link", NS)
        href = link_el.get("href", "") if link_el is not None else ""
        if "/shorts/" in href:
            continue
        vid_el = entry.find("yt:videoId", NS)
        title_el = entry.find("atom:title", NS)
        if vid_el is None or title_el is None or not title_el.text:
            continue
        out.append((vid_el.text, title_el.text.strip()))
    return out


def collect_entries():
    """1순위 채널 페이지, 실패하면 2순위 RSS 로 (videoId, title) 목록을 얻는다."""
    try:
        entries = entries_from_channel_page()
        if entries:
            print(f"채널 페이지에서 {len(entries)}개 수집", file=sys.stderr)
            return entries
        print("채널 페이지에서 영상을 못 찾음 → RSS 시도", file=sys.stderr)
    except Exception as e:
        print(f"채널 페이지 실패({e}) → RSS 시도", file=sys.stderr)

    entries = entries_from_feed()
    print(f"RSS 에서 {len(entries)}개 수집", file=sys.stderr)
    return entries


def main():
    now = datetime.now(KST)

    try:
        entries = collect_entries()
    except Exception as e:
        print("영상 목록 수집 실패:", e, file=sys.stderr)
        sys.exit(1)

    videos = []
    for video_id, title in entries:
        parsed = parse_mass_entry(title)
        if parsed is None:
            print(f"skip (매일미사 아님): {title}", file=sys.stderr)
            continue
        date_str, desc = parsed
        videos.append({
            "videoId": video_id,
            "date": date_str,
            "title": desc or title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
        if len(videos) >= MAX_ITEMS:
            break

    if not videos:
        print("no 매일미사([독서,복음,묵상]) entry found", file=sys.stderr)
        sys.exit(1)

    videos.sort(key=lambda v: v["date"], reverse=True)

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
