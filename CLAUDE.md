# CLAUDE.md

## Git 작업 규칙

- **자동 병합**: 작업을 마치면 사용자에게 다시 묻지 않고 `main`에 바로 병합하고 푸시한다.
  1. 작업 브랜치에 커밋하고 푸시한다.
  2. `git fetch origin main`으로 최신 `main`을 받는다. GitHub Actions의 자동 업데이트 커밋(`chore: update ...`)이 자주 들어오므로, `main`이 앞서 있으면 먼저 작업 브랜치에 `origin/main`을 병합한다.
  3. `git push origin HEAD:main`으로 `main`에 올린다. 강제 푸시(`--force`)는 하지 않는다.
  4. 병합 중 충돌이 나면 멈추고 사용자에게 알린다.
  5. 푸시 후 원격 `main`이 방금 커밋을 가리키는지 확인한다.
- PR은 사용자가 요청할 때만 만든다.
