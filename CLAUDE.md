# CLAUDE.md

## Git 작업 규칙

- **자동 병합**: 작업을 마치면 사용자에게 다시 묻지 않고 `main`에 바로 병합하고 푸시한다.
  1. 작업 브랜치에 커밋하고 푸시한다.
  2. `git fetch origin main`으로 최신 `main`을 받는다. GitHub Actions의 자동 업데이트 커밋(`chore: update ...`)이 자주 들어오므로, `main`이 앞서 있으면 먼저 작업 브랜치에 `origin/main`을 병합한다.
  3. `git push origin HEAD:main`으로 `main`에 올린다. 강제 푸시(`--force`)는 하지 않는다.
  4. 병합 중 충돌이 나면 멈추고 사용자에게 알린다.
  5. 푸시 후 원격 `main`이 방금 커밋을 가리키는지 확인한다.
- PR은 사용자가 요청할 때만 만든다.

## 묵주기도 묵상글 세트 추가 (`rosary-meditation.html`)

다른 단체의 묵주기도 묵상글을 새 세트로 넣을 때:

1. 스크립트 안에 `PAULINE` 처럼 신비별 데이터를 만든다. 키는 `joyful`·`luminous`·`sorrowful`·`glorious`, 각 5단.
   단 항목 필드: `q`(성경 인용), `text`(해설), `ref`(성경 구절), `fruit`(묵상의 열매), `trad:true`(성경 본문이 없는 전승 신비). 필요한 것만 쓴다.
2. `SETS` 배열에 항목을 하나 추가한다: `id`(영문, `?set=id`로 바로 열림), `icon`, `label`, `org`(단체명), `layout`(`'beads'` 묵주알 타임라인 / `'cards'` 접이식 카드), `intro`(선택), `data`, `note`(출처 안내 HTML, 원문 링크 포함).
3. 각 단 제목은 데이터에 넣지 않는다. 모든 세트가 `MYSTERIES`의 『가톨릭 기도서』 제목을 함께 쓴다(홈 카드 `index.html`, `rosary-guide.html`과 글자까지 같게 유지).
4. 원문 사이트가 네트워크에서 막히면 환경의 허용 목록에 그 호스트를 추가해 달라고 요청한다.
