# -*- coding: utf-8 -*-
"""
data/parishes.json 에 등록된 성당 홈페이지들 중, '자동으로 이벤트를
읽어올 수 있는 플랫폼'에 한해 각 성당의 이번 달 행사 목록을 모아
data/parish_events.json 으로 저장한다.

배경
----
방법1(내 성당을 고르면 그 성당만의 특별 미사·행사를 보여 준다)을 위해서는
성당별 이벤트 데이터가 필요하다. data/parishes.json 은 이미 747개 성당의
홈페이지 주소를 갖고 있지만(전국 1,720개 중), 그 주소들을 실제로 열어 보면
플랫폼이 완전히 제각각이다(2026-09 조사 기준):

  다음 카페     301곳 (40%) — 대부분 '본당 주보'를 이미지로만 올려서
                              텍스트로 된 개별 행사 목록이 없다.
  독립 도메인   285곳 (38%) — 성당마다 레이아웃이 전부 달라 일반화 불가.
  catholic.or.kr 58곳 ( 8%) — church.catholic.or.kr/성당명 형태의 20년 전
                              스타일 정적 페이지. 성당마다 구조가 달라
                              표준 파서를 만들 수 없다.
  네이버 카페    53곳 ( 7%) — 다음 카페와 비슷한 상황으로 추정.
  uca.or.kr(*)   44곳 ( 6%) — 의정부교구 공용 플랫폼(sd.uca.or.kr). 모든
                              성당이 같은 캘린더 위젯을 쓰고, 그 안의
                              행사가 'YYYY-MM-DD + 제목' 형태로 구조화돼
                              있어 자동으로 읽어 올 수 있다.
                              (*44곳 중 43곳이 sd.uca.or.kr, 1곳은 도메인만
                               비슷한 다른 사이트라 이번엔 제외한다.)

그래서 지금 자동화하는 것은 sd.uca.or.kr(의정부교구, 43개 성당)뿐이다.
나머지는 이 스크립트가 조용히 건너뛰고, data/parish_events.json 의
'unsupported' 항목에 이유와 개수를 남겨 둔다 — 다음 단계(크라우드소싱 등)를
설계할 때 참고하기 위함이다.

sd.uca.or.kr 구조
-----------------
각 성당 홈페이지(예: sd.uca.or.kr/kyoha/)의 첫 화면에
  <a href="calendar.aspx?mnucd=20001883">월중행사안내</a>
링크가 있다. 이 mnucd 값으로 그 달의 행사 페이지를 요청하면
  <li><span class="data" onclick="location.href='calendar_view.aspx?
      ...&calendar_sdate=2026-09-12'">2026-09-12</a></span>
      민족의 화해와 일치를 위한 미사</li>
형태로 (날짜, 제목) 쌍이 나온다.

GitHub Actions에서 주기적으로 실행됨.
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests

KST = ZoneInfo("Asia/Seoul")
PARISHES_FILE = Path(__file__).resolve().parent.parent / "data" / "parishes.json"
OUT = Path(__file__).resolve().parent.parent / "data" / "parish_events.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
TIMEOUT = 20

MNUCD_RE = re.compile(r"calendar\.aspx\?mnucd=(\d+)")
EVENT_RE = re.compile(
    r"calendar_sdate=(\d{4}-\d{2}-\d{2})'\">[^<]*</a></span>\s*([^<]+?)\s*</li>",
    re.S,
)


def is_uca_parish(homepage: str) -> bool:
    return "sd.uca.or.kr" in homepage


def fetch_month(session: requests.Session, base_url: str, mnucd: str, yyyymm: str) -> list:
    """base_url(성당 홈 주소) 기준으로 그 달의 (날짜, 제목) 목록을 가져온다."""
    # data/parishes.json 의 홈페이지 주소는 끝에 '/'가 있는 것도 없는 것도
    # 섞여 있다. urljoin은 끝에 '/'가 없으면 그 마지막 조각을 '파일명'으로
    # 보고 잘라내 버리므로(예: sd.uca.or.kr/maseok + calendar
    # -> sd.uca.or.kr/calendar, 성당 경로가 통째로 사라짐), 먼저 보정한다.
    if not base_url.endswith("/"):
        base_url += "/"
    url = urljoin(base_url, f"calendar?mnucd={mnucd}&nowmonth={yyyymm}12")
    r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    events = []
    for m in EVENT_RE.finditer(r.text):
        date, title = m.group(1), html.unescape(m.group(2)).strip()
        if title:
            events.append({"date": date, "title": title})
    return events


def fetch_parish_events(session: requests.Session, homepage: str) -> list:
    """성당 홈페이지 하나에서 이번 달·다음 달 행사를 모은다."""
    r = session.get(homepage, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"

    m = MNUCD_RE.search(r.text)
    if not m:
        return []
    mnucd = m.group(1)

    now = datetime.now(KST)
    this_month = f"{now.year:04d}{now.month:02d}"
    ny, nm = (now.year, now.month + 1) if now.month < 12 else (now.year + 1, 1)
    next_month = f"{ny:04d}{nm:02d}"

    events = []
    seen = set()
    for yyyymm in (this_month, next_month):
        try:
            for ev in fetch_month(session, homepage, mnucd, yyyymm):
                key = (ev["date"], ev["title"])
                if key not in seen:
                    seen.add(key)
                    events.append(ev)
        except Exception as e:
            print(f"  {homepage} {yyyymm} 조회 실패: {e}", file=sys.stderr)

    events.sort(key=lambda e: e["date"])
    return events


def main() -> int:
    parishes_doc = json.loads(PARISHES_FILE.read_text(encoding="utf-8"))
    all_parishes = parishes_doc.get("parishes", [])
    with_homepage = [p for p in all_parishes if p.get("homepage", "").strip()]

    from collections import Counter

    def bucket(url: str) -> str:
        u = url.lower()
        if "cafe.daum" in u:
            return "다음 카페"
        if "cafe.naver" in u:
            return "네이버 카페"
        if "blog.naver" in u:
            return "네이버 블로그"
        if "sd.uca.or.kr" in u:
            return "uca.or.kr(자동 수집됨)"
        if "catholic.or.kr" in u:
            return "catholic.or.kr"
        return "독립 도메인"

    unsupported = Counter(
        bucket(p["homepage"]) for p in with_homepage if not is_uca_parish(p["homepage"])
    )

    targets = [p for p in with_homepage if is_uca_parish(p["homepage"])]
    print(f"자동 수집 대상(sd.uca.or.kr): {len(targets)}곳")

    session = requests.Session()
    results = {}
    ok, empty, failed = 0, 0, 0

    for p in targets:
        key = p["homepage"].strip()
        try:
            events = fetch_parish_events(session, key)
        except Exception as e:
            print(f"실패: {p['name']} ({key}) - {e}", file=sys.stderr)
            failed += 1
            continue

        results[key] = {
            "name": p["name"],
            "diocese": p["diocese"],
            "events": events,
        }
        if events:
            ok += 1
        else:
            empty += 1

    print(f"결과: 이벤트 있음 {ok}곳 / 이벤트 없음(정상, 미등록달) {empty}곳 / 요청 실패 {failed}곳")

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "note": (
            "지금은 sd.uca.or.kr(의정부교구 공용 플랫폼) 성당만 자동으로 읽어 온다. "
            "다른 플랫폼은 성당마다 구조가 달라 일반화된 파서를 만들 수 없었다 — "
            "unsupported 항목 참고."
        ),
        "supported_platform": "sd.uca.or.kr",
        "count": len(results),
        "parishes": results,
        "unsupported": dict(unsupported),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
