# -*- coding: utf-8 -*-
"""
가톨릭굿뉴스 '우리들의 묵상/체험' 게시판(menu=4770)에서
지정한 신부님들의 최근 3일간 글(제목 또는 작성자 기준)을 추출하여
data/muksang.json 으로 저장한다.

GitHub Actions에서 주기적으로 실행됨.
※ 본문은 저장하지 않고 제목/작성자/날짜/원문 링크만 저장한다(저작권 존중).
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://maria.catholic.or.kr/mi_pr/missa/"
LIST_URL = BASE + "bbs_list.asp"
MENU = "4770"

# 추출 대상 신부님 (이름만; '신부님' 유무와 무관하게 매칭)
NAMES = ["조명연", "이병우", "김건태", "조욱현", "한상우", "양승국", "이영근"]

DAYS = 3          # 최근 3일
MAX_PAGES = 8     # 안전 상한 (페이지당 약 30여 건)

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "muksang.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": LIST_URL + "?menu=" + MENU,
}


def get_html(session: requests.Session, params: dict) -> str:
    r = session.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    # 서버가 utf-8로 응답하지만, 혹시 모를 인코딩 오판에 대비
    if not r.encoding or r.encoding.lower() in ("iso-8859-1",):
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def parse_rows(html: str):
    """목록 페이지에서 (num, id, title, date, author) 행을 추출."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.select('a[href*="bbs_view.asp"]'):
        href = a.get("href", "")
        m_id = re.search(r"[?&]id=(\d+)", href)
        if not m_id:
            continue
        tr = a.find_parent("tr")
        if tr is None:
            continue
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [td.get_text(" ", strip=True) for td in tds]
        # 날짜 셀 찾기 (yyyy-mm-dd 또는 yy-mm-dd / mm-dd 형식 대응)
        date_str = None
        date_idx = None
        for i, t in enumerate(texts):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
                date_str = t
                date_idx = i
                break
        if date_str is None:
            continue
        title = a.get_text(" ", strip=True)
        # 작성자: 날짜 바로 다음 셀
        author = texts[date_idx + 1] if date_idx + 1 < len(texts) else ""
        if "?" in href:
            url = BASE + "bbs_view.asp" + href[href.index("?"):]
        elif href.startswith("http"):
            url = href
        else:
            url = BASE + href.lstrip("/")
        rows.append({
            "id": m_id.group(1),
            "title": title,
            "author": author,
            "date": date_str,
            "url": url,
        })
    return rows


def main():
    now = datetime.now(KST)
    cutoff = (now - timedelta(days=DAYS - 1)).strftime("%Y-%m-%d")  # 오늘 포함 3일

    session = requests.Session()
    # 세션 확립: 파라미터 없이 기본 목록을 먼저 요청 (세션 없이는 옛 페이지로 리다이렉트되는 경우가 있음)
    all_rows = {}
    try:
        first = get_html(session, {"menu": MENU})
        for r in parse_rows(first):
            all_rows[r["id"]] = r
    except Exception as e:
        print("first page fetch failed:", e, file=sys.stderr)

    stop = False
    for page in range(1, MAX_PAGES + 1):
        if stop:
            break
        try:
            html = get_html(session, {"menu": MENU, "Page": str(page), "SORT": "W"})
        except Exception as e:
            print(f"page {page} fetch failed:", e, file=sys.stderr)
            continue
        rows = parse_rows(html)
        if not rows:
            continue
        dates = [r["date"] for r in rows]
        # 이 페이지 전체가 기준일보다 오래됐으면 이후 페이지는 볼 필요 없음
        if max(dates) < cutoff:
            stop = True
        for r in rows:
            all_rows[r["id"]] = r

    # 최근 3일 + 이름 필터 (제목 또는 작성자에 이름 포함)
    def matched_names(r):
        hay = r["title"] + " " + r["author"]
        return [n for n in NAMES if n in hay]

    posts = []
    for r in all_rows.values():
        if r["date"] < cutoff:
            continue
        names = matched_names(r)
        if not names:
            continue
        r["priest"] = names[0]
        posts.append(r)

    posts.sort(key=lambda r: (r["date"], int(r["id"])), reverse=True)

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "cutoff": cutoff,
        "days": DAYS,
        "names": NAMES,
        "source": LIST_URL + "?menu=" + MENU,
        "count": len(posts),
        "posts": posts,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(posts)} posts (cutoff {cutoff}) -> {OUT}")

    # 수집 자체가 실패한 경우(행이 하나도 없음) 워크플로우가 알 수 있게 실패 처리
    if not all_rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
