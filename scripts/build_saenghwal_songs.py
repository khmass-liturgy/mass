# -*- coding: utf-8 -*-
"""
'오늘의 떼제 · 생활성가' 카드의 생활성가 목록을 만든다 → data/saenghwal_songs.json

YouTube에서 조회수가 많은 가톨릭 생활성가 가운데, 한 곡짜리(2분 30초~7분) 영상을
사람이 골라 아래 PICKS 에 적어 두었다. 이 스크립트는 곡마다
  - oEmbed 로 영상이 아직 살아 있는지(삭제·비공개면 뺀다)
  - 재생 화면을 읽을 수 있으면 한국에서 재생되는지(playabilityStatus)와 길이·조회수
를 확인하고, 조회수 순으로 저장한다. YouTube가 자동 요청을 막아 재생 화면을 못 읽으면
길이·조회수는 지난번 값을 그대로 쓴다.

고르는 기준
  - 가톨릭 생활성가 (개신교 CCM·복음성가는 넣지 않는다)
  - 1시간짜리 모음·기도문 낭독·뉴스처럼 한 곡이 아닌 영상은 넣지 않는다
  - 같은 곡은 조회수가 가장 많은 영상 하나만

화면(index.html)은 이 목록에서 한국 날짜 기준으로 하루에 한 곡을 골라 보여 준다.
목록은 자주 바뀌지 않으므로 곡을 더하거나 뺄 때 손으로 한 번 실행한다.
  python scripts/build_saenghwal_songs.py
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "saenghwal_songs.json"
KST = ZoneInfo("Asia/Seoul")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Cookie": "CONSENT=YES+1; PREF=gl=KR&hl=ko",
}

# (영상 id, 곡명, 부른 이)
PICKS = [
    ("7Xwlt-2JUak", "성모님께 바치는 노래", "기도를 켜다"),
    ("M_TiaOBeCzw", "주님의 기도", "기도를 켜다"),
    ("pxrMdVsw6E0", "아무것도 너를", "열일곱이다"),
    ("DUiuHoBmm1k", "난 네가 좋다", "열일곱이다"),
    ("AJUMwcZNLwk", "하느님은 너를 지키시는 분", "노래해주리"),
    ("pewjD1abYXg", "사랑하는 그대에게", "열일곱이다"),
    ("U2eD-vxLDdU", "그 길", "기도를 켜다"),
    ("-WbbwEyJ3KQ", "하느님 당신은 나의 모든 것", "노래해주리"),
    ("gQLNCRykJbU", "임마누엘", "노래해주리"),
    ("FcMqITwuI5Y", "꽃", "기도를 켜다"),
    ("DLL3RDUfyXg", "구원자 예수 너의 사랑", "열일곱이다"),
    ("mnGc9Pf_8S4", "고백 - 하늘바라기", "열일곱이다"),
    ("buvLW0ULuj0", "누군가 널 위해 기도하네", "노래해주리"),
    ("KA0D0IfVFvg", "소중한 사람을 위한 기도", "열일곱이다"),
    ("TEwf7gAICZI", "아버지", "노래해주리"),
    ("Bg5GECvt7nE", "기대", "기도를 켜다"),
    ("4-sbfU7Fw2Y", "이는 내 사랑하는 아들이니", "노래해주리"),
    ("Ir1BMC6V8NU", "사랑의 송가", "열일곱이다"),
    ("RA4QJ9usUOk", "하늘의 태양은 못 되더라도", "권용석 아마데오"),
    ("7HjPVuyIvnk", "엄마의 기도가 하늘에 닿으면", "열일곱이다"),
    ("AR1ekJwHeXg", "완전한 사랑", "열일곱이다"),
    ("BaYDYFkj318", "임쓰신 가시관", "갓등중창단"),
    ("2k2AdSMlESA", "갈림 없는 마음", "열일곱이다"),
    ("aQvYvTjCflg", "처음과 같이 끝에서도", "열일곱이다"),
    ("DhCrO_hoWfs", "예수 내 작은 기쁨", "열일곱이다"),
    ("6Ujog13ouMs", "삼위일체", "기도를 켜다"),
    ("9CGOu8Jyi_g", "풀꽃의 노래", "잔꽃송이(예수성심시녀회)"),
    ("LQ16b6ys1Bs", "나는 살아서도 죽어서도", "노래해주리"),
    ("pXeSg6f5mpI", "소명", "열일곱이다"),
    ("XTm4Wa1scmI", "힘을 내라", "한덕훈 신부"),
    ("hRzQX0cdkc8", "나는 천주교인이오", "서울가톨릭싱어즈"),
    ("AJMEgEbbJh0", "내 발을 씻기신 예수", "갓등중창단"),
    ("_MXioVgyq0w", "마음을 드높이", "제이팸"),
    ("8X3VIPS4j_I", "귀천 (순교자의 기도)", "열일곱이다"),
    ("6VbwrLAGINI", "당신만으로 충분합니다", "열일곱이다"),
    ("NVRTyuaLfng", "복음의 기쁨", "열일곱이다"),
    ("OIP0iN9EXd4", "참 아름다운 그대", "기도를 켜다"),
    ("vDbgMVR0r8s", "축제", "제이팸"),
    ("cTAzOPI63OQ", "로고스 찬가", "윤요셉 신부"),
    ("KSSzGK0mWBA", "영원히 너의 곁에", "바오로딸"),
    ("jn1spkmwVFI", "내 곁에, 부활", "갓등중창단"),
    ("lvprSY8X8ZM", "평화의 도구로 써주소서", "열일곱이다"),
    ("56dIQfrRDo4", "기뻐하고 즐거워하여라", "열일곱이다"),
    ("dzbToVAbppA", "오 주여 나의 마음이", "성바오로딸수도회"),
    ("p8ZaiMR-d68", "그대입니다", "제이팸"),
    ("FgRdkckXMjc", "수도 삶", "꽃동네 수도자 찬미단"),
    ("Uvqm6sv7k24", "십자가 길에서", "꽃동네 수도자 찬미단"),
    ("-o8WE5XjDrw", "성모의 노래", "나무밴드"),
]


def oembed_alive(vid):
    """oEmbed 로 영상이 살아 있는지 본다. 지워졌거나 비공개면 404/400. 판단이 안 되면 None."""
    url = ("https://www.youtube.com/oembed?format=json&url="
           f"https://www.youtube.com/watch?v={vid}")
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code in (404, 400):
                return False
            if r.status_code in (200, 401):   # 401 은 '퍼가기 금지'일 뿐 YouTube 에서는 재생된다
                return True
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    return None


def watch_info(vid):
    """재생 화면에서 (재생 상태, 길이 초, 조회수)를 읽는다.
    YouTube가 자동 요청을 막으면(google.com/sorry 로 넘김) (None, None, None)."""
    url = f"https://www.youtube.com/watch?v={vid}&gl=KR&hl=ko"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=False)
    except requests.RequestException:
        return (None, None, None)
    if r.status_code != 200:
        return (None, None, None)
    t = r.text
    st = re.search(r'"playabilityStatus":\{"status":"([A-Z_]+)"', t)
    ln = re.search(r'"lengthSeconds":"(\d+)"', t)
    vc = re.search(r'"viewCount":"(\d+)"', t)
    return (st.group(1) if st else None,
            int(ln.group(1)) if ln else None,
            int(vc.group(1)) if vc else None)


def main():
    # 재생 화면을 못 읽을 때를 위해 지난번에 저장한 길이·조회수를 기억해 둔다.
    prev = {}
    if OUT.exists():
        try:
            prev = {x["videoId"]: x for x in json.loads(OUT.read_text(encoding="utf-8")).get("items", [])}
        except (ValueError, KeyError):
            prev = {}

    items, skipped = [], []
    for vid, title, artist in PICKS:
        alive = oembed_alive(vid)
        if alive is False:
            skipped.append(f"{vid} {title} (삭제·비공개)")
            continue
        status, length, views = watch_info(vid)
        if status and status != "OK":            # 한국에서 재생이 막힌 영상 등
            skipped.append(f"{vid} {title} ({status})")
            continue
        old = prev.get(vid, {})
        items.append({
            "title": title,
            "artist": artist,
            "videoId": vid,
            "duration": length or old.get("duration"),
            "views": views or old.get("views"),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
        time.sleep(0.5)

    if not items:
        print("살아 있는 곡이 하나도 없어 파일을 바꾸지 않았습니다.", file=sys.stderr)
        return 1
    items.sort(key=lambda x: -(x["views"] or 0))
    out = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": "YouTube 가톨릭 생활성가 (조회수 많은 곡을 골라 정리)",
        "count": len(items),
        "items": items,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(items)}곡 저장")
    for s in skipped:
        print("  뺀 곡:", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
