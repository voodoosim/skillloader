# Gate 6 Handoff — eager vs SkillLoader 비교 실험

**To**: 쟤 (Codex)
**From**: Claude (Opencode)
**Date**: 2026-07-21
**Base branch**: `main` at `782d2b3`; 아래 증거 변경은 아직 미커밋

## 현재 상태

- Gate 0~5: 전부 완료
- Gate 6: live Codex 12태스크 × eager/MCP 2설정 실행 및 정제된 결과 기록 완료
- Gate 7: 아직 시작 안 함

## 완료된 작업

### 실제 비교 측정

1. `bench/tasks/task-fixture-v1.json` 기반으로 실제 Codex 클라이언트에서 두 설정 비교
2. 설정 A (eager): 10개 parity 스킬 전부 developer instructions에 주입
3. 설정 B (SkillLoader): `SKILLLOADER_ROOTS="testdata/parity/home/.codex/skills"` 로 MCP 서버 기동 → search → load 패턴
4. 12태스크 × 2설정 = 24회 측정
5. 지표: top-1 정확도, 카탈로그 오버헤드 토큰, 총 입력 토큰, 라우팅 실패율
6. 격리 결과 JSON을 `bench/results/2026-07-21-codex-0.144.6-gate6-isolated/`에 기록

결과와 제한은 `docs/PRODUCT_EVIDENCE.md`에 기록했다. 24/24 프로세스
실행은 성공했지만 작은 카탈로그에서 SkillLoader total input은 eager보다
242.84% 증가했다. 태스크 완수와 대형 카탈로그 break-even은 미검증이다.
기존 `-gate6/` 결과는 전역 `AGENTS.md` 혼입으로 비교 근거에서 제외했다.

### 후속 작업

- 비교 프로토콜 + 측정 지표 상세 설계
- `docs/PRODUCT_EVIDENCE.md` 생성
- Claude Code/OpenCode 실측
- 반복 실행 통계와 대형 카탈로그 break-even

### 작업 상태

- 브랜치: `main`
- 결과·실행기·문서 변경: 미커밋
- 독립 미커밋 리뷰 지적 44건 반영; 최종 재검토 우선순위 결함 0건

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
- [x] eager 등록과 SkillLoader를 같은 모델·작업·카탈로그 조건에서 비교
- [x] 카탈로그 오버헤드, 라우팅 작업 오버헤드, 총 입력 토큰을 분리
- [x] top-1, top-5, 오로드, 미로드 지표를 보고
- [ ] 원시 입력과 기계 판독 결과를 커밋 (현재 작업 트리에만 기록;
  커밋 시 저장소의 미커밋 상태 표기도 함께 갱신)
```

체크된 항목은 현재 작업 트리의 증거 기준이며, 커밋·릴리스 검증은 별도다.
