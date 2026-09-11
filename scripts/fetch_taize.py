# -*- coding: utf-8 -*-
"""
YouTube의 'Taizé - 주제'(Topic) 채널 — 떼제 공동체 음원의 공식 배급사가
YouTube에 자동으로 만들어 주는 채널로, 앨범(재생목록) 단위로 성가 트랙이
올라와 있다 — 에서 3~5분가량의 개별 성가 영상을 모아
data/taize.json 으로 저장한다.

카드에서 무엇을 보여 줄지는 화면(index.html)이 정한다. 여기서는 '성가
전체 목록'만 만들어 두고, 그중 하루에 한 곡을 골라 보여 주는 일은
화면 쪽에서 한국 날짜를 기준으로 처리한다 (가톨릭신문 기획특집 카드와
같은 방식).

수집 방식
---------
1) 채널의 '재생목록' 탭에서 앨범(재생목록) id 목록을 얻는다.
2) 앨범마다 재생목록 페이지를 열어, 그 안의 영상들(제목 · 영상id ·
   길이)을 읽는다. 길이는 영상을 따로 열어 보지 않아도 재생목록
   페이지의 썸네일 뱃지에 'M:SS' 형태로 이미 나와 있다.
3) 3~5분 안팎(2:30~5:30, '가량'을 감안한 여유)에 드는 것만 남기고,
   해설·인터뷰·티저 같은 노래가 아닌 보너스 트랙은 제목으로 걸러낸다.

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
# 'Taizé - 주제(Topic)' 채널 — 떼제 공식 음원의 배급사가 YouTube에
# 자동으로 만든 채널이다. 채널 자체에는 영상이 없고 앨범(재생목록)만 있다.
CHANNEL_ID = "UChsu1sFF1boxTdEyX3pY2FA"
PLAYLISTS_URL = f"{BASE}/channel/{CHANNEL_ID}/playlists"

# '약 3~5분'의 여유 범위. 딱 3:00~5:00 으로 자르면 마니피캇(2:50),
# 베네딕투스(2:41) 같은 사랑받는 짧은 성가가 빠지므로 양쪽으로 조금 넉넉히 잡는다.
MIN_SECONDS = 150   # 2:30
MAX_SECONDS = 330   # 5:30

# 노래가 아닌 보너스 트랙(해설·인터뷰·티저 등)을 제목으로 걸러낸다.
NON_SONG_RE = re.compile(
    r"\b(background|interview|teaser|tutorial|rehearsal|practice|"
    r"reading|spoken|documentary|trailer|introduction)\b",
    re.IGNORECASE,
)

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "taize.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

INITIAL_DATA_RE = re.compile(r"var ytInitialData = (\{.*?\});</script>", re.S)


def get_json(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    m = INITIAL_DATA_RE.search(r.text)
    if not m:
        raise ValueError(f"ytInitialData를 찾지 못함: {url}")
    return json.loads(m.group(1))


def find_lockups(data, content_type: str) -> list:
    """ytInitialData 트리에서 원하는 종류(영상/재생목록)의 lockupViewModel 을 모은다."""
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


def parse_duration_text(text: str):
    """'3:32' 또는 '1:02:03' 형태를 초로 바꾼다. 라이브 등 텍스트면 None."""
    parts = text.strip().split(":")
    if not all(p.isdigit() for p in parts):
        return None
    parts = [int(p) for p in parts]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def duration_of(lockup: dict):
    """썸네일 하단 뱃지(길이 표시)에서 'M:SS' 텍스트를 찾는다."""
    try:
        overlays = lockup["contentImage"]["thumbnailViewModel"]["overlays"]
    except (KeyError, TypeError):
        return None
    for ov in overlays:
        badges = ov.get("thumbnailBottomOverlayViewModel", {}).get("badges", [])
        for b in badges:
            text = b.get("thumbnailBadgeViewModel", {}).get("text", "")
            secs = parse_duration_text(text)
            if secs is not None:
                return secs
    return None


def fetch_album_playlists() -> list:
    """채널의 '재생목록' 탭에서 앨범(재생목록) id·이름을 모은다."""
    data = get_json(PLAYLISTS_URL)
    albums = []
    for lv in find_lockups(data, "LOCKUP_CONTENT_TYPE_ALBUM"):
        pid = lv.get("contentId")
        title = lv.get("metadata", {}).get("lockupMetadataViewModel", {}) \
                   .get("title", {}).get("content", "")
        if pid:
            albums.append((pid, title))
    return albums


def fetch_album_tracks(playlist_id: str, album_title: str) -> list:
    """앨범(재생목록) 하나에서 3~5분가량의 성가 트랙만 뽑는다."""
    data = get_json(f"{BASE}/playlist?list={playlist_id}")
    tracks = []
    for lv in find_lockups(data, "LOCKUP_CONTENT_TYPE_VIDEO"):
        video_id = lv.get("contentId")
        title = lv.get("metadata", {}).get("lockupMetadataViewModel", {}) \
                   .get("title", {}).get("content", "").strip()
        if not video_id or not title:
            continue
        if NON_SONG_RE.search(title):
            continue
        secs = duration_of(lv)
        if secs is None or not (MIN_SECONDS <= secs <= MAX_SECONDS):
            continue
        tracks.append({
            "title": title,
            "videoId": video_id,
            "duration": secs,
            "album": album_title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    return tracks


def main() -> int:
    try:
        albums = fetch_album_playlists()
        if not albums:
            raise ValueError("앨범(재생목록) 목록을 하나도 찾지 못했습니다.")

        by_video_id = {}
        for pid, album_title in albums:
            for t in fetch_album_tracks(pid, album_title):
                # 같은 성가가 여러 앨범에 실려도(예: 베스트 모음), 같은 영상이면 한 번만 남긴다.
                by_video_id.setdefault(t["videoId"], t)

        if not by_video_id:
            raise ValueError("3~5분가량의 성가 영상을 하나도 찾지 못했습니다.")

        # videoId 순 정렬로 매 실행마다 순서를 고정한다 — 화면의 요일 회전이
        # 안정적으로 같은 순서를 보게 하기 위함이다.
        items = [by_video_id[k] for k in sorted(by_video_id)]

    except Exception as e:
        print("taize fetch/parse failed:", e, file=sys.stderr)
        return 1

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": PLAYLISTS_URL,
        "count": len(items),
        "items": items,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("saved:", OUT, f"({len(items)}곡)")
    # Windows 콘솔(cp949)은 유럽어 특수문자를 못 찍는 경우가 있어 안전하게 처리한다.
    for it in items[:10]:
        m, s = divmod(it["duration"], 60)
        line = f"   {m}:{s:02d}  {it['title']}  [{it['album']}]"
        print(line.encode(sys.stdout.encoding or "utf-8", errors="replace")
                  .decode(sys.stdout.encoding or "utf-8"))
    if len(items) > 10:
        print(f"   ... 외 {len(items) - 10}곡")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
