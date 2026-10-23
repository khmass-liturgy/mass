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
4) 남은 영상마다 실제 재생 페이지의 재생 가능 여부(playabilityStatus)를
   확인해, 재생목록에는 있지만 열면 '동영상을 재생할 수 없음'인 영상을
   자동으로 뺀다. (예전에는 막힌 영상 id 를 사람이 BLOCKED_VIDEO_IDS 에
   적어 넣어야 했다.) 화면(index.html)도 보여 주기 직전에 한 번 더
   확인하므로, 다음 갱신 전에 새로 막힌 영상도 건너뛴다.

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import re
import sys
import time
from datetime import date, datetime
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

# 아랍어 성가는 제목이 아랍 문자가 아니라 로마자 음역(예: 'Ehfazny Rabby')으로
# 올라와 있어서, 유니코드 스크립트 판별로는 걸러지지 않는다. 'Remain With Me'
# 앨범에 프랑스어·영어·스페인어 성가와 섞여 있는 아랍어 성가 제목을 직접
# 나열해 둔다 — 화면(index.html)에서 한국어 사용자에게 매일 하나씩 보여 줄 때
# 아랍어 성가가 나오지 않도록 하기 위함이다.
ARABIC_TITLES = {
    "Ehfazny Rabby",
    "Nasjoudou Laka Ya Rabb",
    "Haloumma Ya Rouh Allah",
    "Haloummou Ya Shou'bou",
    "Sayyidy Anta Liya'lqouwwa",
    "Alzalamou Laysa Zalaman",
    "Omkouthou Wa'sharou Ma'y",
    "Abana Fy Yadayka",
}

# 재생목록에는 그대로 올라와 있지만(제목·길이 정상) 실제로 열어 보면
# '동영상을 재생할 수 없음'으로 막혀 있는 영상들. 권리자 측 사정으로
# 생기는 것으로 보이며, 목록 재수집만으로는 걸러지지 않아 직접 적어 둔다.
# (영상 id : 막힌 걸 확인한 날짜)
BLOCKED_VIDEO_IDS = {
    "ZrMcR7Ct-Pk",  # 2026-10-01 재생 불가 확인
}

# 재생 가능 여부 점검에서 '확실히 못 본다'고 볼 상태. LOGIN_REQUIRED(봇 확인
# 등)나 점검 자체의 실패는 영상 문제가 아닐 수 있으므로 막힌 것으로 치지 않는다.
UNPLAYABLE_STATUSES = {"UNPLAYABLE", "ERROR"}
# 점검에 걸린 영상이 이 비율을 넘으면 영상이 아니라 점검 쪽 문제로 보고 되돌린다.
RECHECK_DAYS = 14   # 같은 영상의 재생 가능 여부를 다시 확인하는 주기
MAX_CHECKS = 200    # 한 번 실행에 확인할 영상 수 상한(요청이 몰려 429 를 받지 않도록)
PLAYABILITY_RE = re.compile(r'"playabilityStatus":\{"status":"([A-Z_]+)"')
# 영상마다 '재생되는 나라' 목록이 들어 있다. Topic 채널 음원은 권리 사정으로 2~4개국에서만
# 재생되는 영상이 많은데, 이런 영상은 재생목록에는 정상으로 올라와 있고 GitHub Actions 서버
# (미국 등)에서 열면 playabilityStatus 도 OK 로 나온다. 그래서 상태만 보면 한국에서 막힌
# 영상을 못 거르고, 나라 목록에 한국이 없는지를 따로 확인해야 한다.
AVAILABLE_COUNTRIES_RE = re.compile(r'"availableCountries":\[([^\]]*)\]')
PLAY_COUNTRY = "KR"

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
        if title in ARABIC_TITLES:
            continue
        if video_id in BLOCKED_VIDEO_IDS:
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


def check_playable(video_id: str):
    """한국에서 재생되는 영상이면 True, 안 되면 False, 확인이 안 되면 None.

    YouTube 가 요청을 몰아서 보내면 429(너무 많은 요청)를 돌려준다. 이걸 '문제 없음'으로
    넘기면 막힌 영상이 그대로 추천되므로, 잠시 기다렸다 다시 해 보고 그래도 안 되면
    None 으로 돌려 호출한 쪽이 지난 판정을 쓰게 한다."""
    for wait in (0, 6, 20):
        time.sleep(wait)
        try:
            r = requests.get(
                f"{BASE}/watch?v={video_id}",
                headers={**HEADERS, "Cookie": "CONSENT=YES+1; SOCS=CAI"},
                timeout=30,
            )
        except requests.RequestException:
            continue
        if r.status_code == 404:
            return False
        if r.status_code != 200:
            continue
        c = AVAILABLE_COUNTRIES_RE.search(r.text)
        if c:
            return f'"{PLAY_COUNTRY}"' in c.group(1)
        m = PLAYABILITY_RE.search(r.text)
        if m:
            return m.group(1) not in UNPLAYABLE_STATUSES
        return None
    return None


def drop_unplayable(by_video_id: dict, checked: dict, today: str) -> dict:
    """한국에서 재생이 안 되는 영상을 뺀다.

    영상 한 편의 재생 가능 여부는 좀처럼 바뀌지 않으므로, 판정을 checked 에 날짜와 함께
    남겨 두고 RECHECK_DAYS 가 지났거나 판정이 없는 영상만 다시 확인한다(한 번에
    MAX_CHECKS 편까지, 오래된 것부터). 이렇게 해야 요청이 적어 429 를 피하고,
    확인이 일시적으로 실패해도 지난 판정이 남아 막힌 영상이 되살아나지 않는다."""
    def age(vid):
        rec = checked.get(vid)
        return (today_ord - date.fromisoformat(rec["at"]).toordinal()) if rec else 10**6

    today_ord = date.fromisoformat(today).toordinal()
    due = sorted((v for v in by_video_id if age(v) >= RECHECK_DAYS), key=age, reverse=True)
    failed = 0
    for vid in due[:MAX_CHECKS]:
        ok = check_playable(vid)
        if ok is None:
            failed += 1
        else:
            checked[vid] = {"ok": ok, "at": today}
        time.sleep(0.5)
    if due:
        print(f"재생 확인: 대상 {len(due)}편 중 {min(len(due), MAX_CHECKS)}편 확인, 실패 {failed}편",
              file=sys.stderr)

    kept = {}
    for vid, t in by_video_id.items():
        if checked.get(vid, {}).get("ok", True):
            kept[vid] = t
        else:
            print(f"  재생 불가로 제외: {vid} {t['title'].encode('ascii', 'replace').decode()}")
    # 판정 기록은 지금 목록에 있는 영상 것만 남긴다.
    for vid in list(checked):
        if vid not in by_video_id:
            del checked[vid]
    return kept


def load_checked() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8")).get("checked", {})
    except (OSError, ValueError):
        return {}


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

        checked = load_checked()
        by_video_id = drop_unplayable(by_video_id, checked, datetime.now(KST).strftime('%Y-%m-%d'))
        if not by_video_id:
            raise ValueError("재생 가능한 성가 영상이 하나도 없습니다.")

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
        "checked": checked,
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
