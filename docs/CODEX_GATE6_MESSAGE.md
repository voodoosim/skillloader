# Gate 6 전달 메시지

## 읽는 순서

1. 이 문서를 먼저 읽는다.
2. 이어서 `docs/HANDOFF_GATE6.md`를 읽는다.
3. 측정 규칙은 `docs/PRODUCT_EVIDENCE.md`만 따른다.

모르는 값은 추측하지 말고 `확인 필요`로 남긴다. 작업 결과는 같은 문서의
“완료 후” 요구사항에 맞춰 짧게 보고한다.

현재 작업 브랜치: `main` at `782d2b3`; Gate 6 증거 변경은 아직 미커밋

`docs/HANDOFF_GATE6.md`를 기준으로 Gate 6을 계속 진행해줘.

## 현재까지 확인한 것

- 합성 fixture의 Go cold/warm 성능 측정은 완료됐다.
- `go vet ./...`, `go test -count=1 ./...`, `go test -race -count=1 ./...`는 통과했다.
- Codex CLI `0.144.6`의 live eager/MCP 비교는 2026-07-21 실행 완료했다.
- Claude Code는 미로그인이고 OpenCode는 동일 모델 조건을 검증하지 않아 비교에서 제외했다.
- 정식 결과는 `bench/results/2026-07-21-codex-0.144.6-gate6-isolated/`와
  `docs/PRODUCT_EVIDENCE.md`를 기준으로 한다.
- 기록된 10-skill 결과 범위를 넘어선 양의 토큰 절감, 대형 카탈로그
  break-even, 태스크 완수 품질은 아직 주장하면 안 된다.

## 네가 이어서 할 일

1. Claude와 OpenCode provider 인증이 가능한 환경에서 `bench/tasks/task-fixture-v1.json`의 12개 태스크를 eager와 SkillLoader 각각 실행한다.
2. 두 설정에서 모델, system instructions, 카탈로그, 사용자 입력, sampling 조건을 동일하게 유지한다.
3. `docs/PRODUCT_EVIDENCE.md`의 결과 형식대로 `bench/results/<date>-<client>-gate6/`에 원시 결과와 `summary.json`을 저장한다.
4. top-1/top-5, no-load, incorrect-load, routing failure, catalog overhead, total input tokens를 분리 보고한다.
5. 실제 측정이 계속 불가능하면 추측으로 수치를 만들지 말고, 인증 부족과 재개 조건만 문서에 남긴다.

완료 후 커밋 해시, 실행한 클라이언트·모델, 결과 경로, 미검증 항목을 보고해줘.
