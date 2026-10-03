# -*- coding: utf-8 -*-
"""
Firebase(Firestore)에 저장된 세례명 축일 데이터를 feast_days.json 으로 복사한다.

관리 페이지(feastday-admin.html)는 Firestore 에만 저장하고, 일반 화면은
Firestore 를 먼저 읽되 실패하면 이 파일로 대신한다. 그래서 이 파일이
너무 옛날 내용이 되지 않도록 주기적으로 맞춰 둔다.

Firestore 가 비었거나 내용이 이상하면 기존 파일을 건드리지 않는다.
GitHub Actions에서 주기적으로 실행됨.
"""

import json
import sys
from pathlib import Path

import requests

PROJECT = "khmass-jeonrye"
API_KEY = "AIzaSyB_XOy_6SqlWptnDRlX7oGESTyjqW2dN3A"  # 웹 앱 공개 키(보안은 Firestore 규칙이 담당)
URL = (f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
       f"/databases/(default)/documents/feastday/data?key={API_KEY}")
OUT = Path(__file__).resolve().parent.parent / "feast_days.json"


def main() -> int:
    try:
        r = requests.get(URL, timeout=30)
        r.raise_for_status()
        data = json.loads(r.json()["fields"]["json"]["stringValue"])
        saints = data["saints"]
        if not isinstance(saints, list) or len(saints) < 100:
            raise ValueError(f"축일 건수가 이상합니다: {len(saints)}")
    except Exception as e:
        print("sync failed, 기존 파일 유지:", e, file=sys.stderr)
        return 1

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") == text:
        print("no change")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"saved {len(saints)}건 -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
