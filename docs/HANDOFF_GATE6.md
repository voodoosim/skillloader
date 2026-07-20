# Gate 6 Handoff — eager vs SkillLoader 비교 실험

**To**: 쟤 (Codex)
**From**: Claude (Opencode)
**Date**: 2026-07-21
**Base branch**: `main` at `e4183b0`

## 현재 상태

- Gate 0~5: 전부 완료
- Gate 6: `bench/tasks/task-fixture-v1.json` (12태스크, 7카테고리) + `docs/BENCHMARK.md` 갱신 완료
- Gate 7: 아직 시작 안 함

## 당신에게 맡길 작업

### 우선순위 A: 실제 비교 측정

1. `bench/tasks/task-fixture-v1.json` 기반으로 실제 Codex/Opencode 클라이언트에서 두 설정 비교
2. 설정 A (eager): 10개 parity 스킬 전부 시스템 프롬프트에 주입
3. 설정 B (SkillLoader): `SKILLLOADER_ROOTS="testdata/parity/home/.codex/skills"` 로 MCP 서버 기동 → search → load 패턴
4. 12태스크 × 2설정 = 24회 측정
5. 지표: top-1 정확도, 카탈로그 오버헤드 토큰, 총 입력 토큰, 라우팅 실패율
6. 결과 JSON을 `bench/results/` 에 기록

### 우선순위 B: 방법론 문서 (A가 불가능할 경우)

- 비교 프로토콜 + 측정 지표 상세 설계
- `docs/PRODUCT_EVIDENCE.md` 생성
- 실제 측정은 이후

### 작업 방식

- 브랜치: `codex/gate6-evidence` (main 기준 새로 생성)
- 완료 후 `worker_done` 전송
- 둘 다 가능하면 A안 우선

## 참고 파일

- `bench/tasks/task-fixture-v1.json` — 12개 태스크 정의
- `testdata/parity/` — 10개 합성 스킬 카탈로그
- `docs/BENCHMARK.md` — 벤치마크 방법론
- `docs/PARITY.md` — 파이썬-GO 정합성 결과
- `docs/MCP_CONTRACT.md` — search/load 스키마

## 현재 Gate 6 체크리스트 (plan.md)

```
Gate 6 — 제품 근거
- [x] 합성 fixture에서 cold·warm 검색과 로드의 p50·p95를 재현 가능한 방식으로 측정
- [ ] eager 등록과 SkillLoader를 같은 모델·작업·카탈로그 조건에서 비교
- [ ] 카탈로그 오버헤드, 라우팅 작업 오버헤드, 총 입력 토큰을 분리
- [ ] top-1, top-5, 오로드, 미로드 지표를 보고
- [ ] 원시 입력과 기계 판독 결과를 저장소에 기록
```

당신이 위 □ 항목을 담당하게 됩니다.
