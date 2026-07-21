# SkillLoader 독립 프로젝트 계획

## 1. 계획 기준

이 문서는 SkillLoader를 기존 Codex 설정 작업의 연장이 아닌 독립
프로젝트로 새로 개발하기 위한 실행 계획이다.

- 최초 아이디어와 단계 구조는 `CODEX_PLAN_BASELINE.md`를 참고한다.
- 기존 커밋의 Go 코드와 문서는 완료된 구현이 아니라 검토 가능한 참고
  자산으로 취급한다.
- 기존 계획의 완료 표시는 승계하지 않는다.
- 코드 재사용 여부는 이 문서의 테스트와 검토를 통과한 뒤 결정한다.
- 제품 주장, 호환성, 토큰 절감률, 성능 수치는 새 증거로만 인정한다.

## 2. 프로젝트 목표

하나의 Go 바이너리 `skillloader`가 신뢰된 로컬 루트의 스킬 목록을
관리하고, 모델에는 다음 두 MCP 도구만 노출한다.

- `search_skills`: 제한된 개수의 관련 스킬 메타데이터 검색
- `load_skill`: 검색 결과의 논리 이름으로 전체 `SKILL.md` 로드

운영자 기능은 모델 컨텍스트와 분리해 CLI로 제공한다.

- `skillloader list`
- `skillloader doctor`

MVP는 로컬 stdio 전송만 지원한다. HTTP, Docker, 원격 카탈로그,
마켓플레이스, 임베딩 검색은 MVP 검증 이후로 미룬다.

## 3. 제품 불변 조건

- 전체 스킬 카탈로그를 모델의 상시 컨텍스트에 넣지 않는다.
- 검색 결과 수는 항상 제한한다.
- 클라이언트가 임의 파일 경로를 전달할 수 없게 한다.
- 스킬은 논리 이름으로만 식별한다.
- 파일 해석은 설정된 신뢰 루트 내부로 제한한다.
- 루트 이탈, 경로 순회, 심볼릭 링크 이탈, 중복 이름을 거부한다.
- 캐시는 지연시간 최적화로만 평가하며 토큰 절감 근거로 사용하지 않는다.
- 오류에는 로컬 절대 경로, 환경값, 비밀정보를 포함하지 않는다.
- 측정 자료가 없으면 토큰 절감·호환성·성능 완료를 주장하지 않는다.

## 4. 독립 프로젝트 작업 방식

### Git과 AI 협업

- `main`은 검증된 통합 커밋만 받는다.
- 구현 AI마다 별도 worktree와 작업 브랜치를 사용한다.
- 브랜치는 한 가지 변경 목적만 가진다.
- 검토 요청에는 기준 커밋, 대상 커밋, 변경 파일, 검증 명령, 남은 문제를
  `HANDOFF.md`에 기록한다.
- 검토 AI는 대상 커밋을 기준으로 재현하고, 근거 없는 완료 표시를 승인하지
  않는다.
- 같은 파일을 여러 AI가 동시에 수정하지 않는다.
- 병합 전 구현자 테스트와 독립 검토를 모두 통과한다.

### 완료 판정

항목은 다음 증거가 모두 있을 때만 `[x]`로 바꾼다.

1. 구현 또는 문서 변경이 실제 파일에 존재한다.
2. 해당 항목을 직접 검증하는 명령이나 테스트가 통과한다.
3. `HANDOFF.md`에 실행 명령과 결과가 기록된다.
4. 독립 검토에서 치명적·높음 등급 문제가 남지 않는다.

## 5. 단계별 실행 계획

### Gate 0 — 새 프로젝트 기준선

- [x] GitHub 소유자와 공개 Go 모듈 경로를 결정한다.
- [x] 라이선스를 결정하고 저장소에 추가한다.
- [x] Go 버전과 `GOPATH == GOROOT` 경고 처리 방침을 결정한다.
- [x] 기존 코드의 파일별 재사용·재작성·폐기 판단표를 작성한다.
- [x] MCP SDK 버전과 선택 근거를 기록한다.
- [x] 새 프로젝트 기준 커밋을 만들고 `main`을 깨끗하게 유지한다.

#### 코드 자산 감사표

Python `skill-loader/scripts/skill_loader.py` (5,397글자, 87스킬 인덱스)와
그 주변 유틸리티를 기준으로 판정.

| 파일 | 판정 | 근거 |
|---|---|---|
| `search.go` | 재작성 | Python의 `skill_search` 로직을 8레이어 파이프라인 + dedup·safety filter로 재구현. 평가 가중치와 토큰 규칙은 Go 전용으로 재정의 |
| `catalog.go` | 재작성 | Python의 `candidate_skill_paths`, `read_skill_metadata`, `validate_tag_index`를 Go 모듈화. `os.OpenRoot` 기반 샌드박스 탐색으로 전환, YAML 파서는 yaml.v3 도입 |
| `loader.go` | 재작성 | Python의 `load_skill_content`, `resolve_skill_path` → Go `readTrustedFile` (3계층 containment: Rel→EvalSymlinks→OpenRoot). 경로 탈출 방어 추가 |
| `cache.go` | 재작성 | Python의 `_skill_data_cache`, `_index_cache` → Go `Cache` (caller-provided checksum으로 I/O 제거). `StoreIndex`는 입력 복사본 보존 |
| `doctor.go` | 재작성 | Python `candidate_skill_paths` 결과와 Claude CLI `skill-loader list` 출력을 Go 구조체 + JSON으로 통합 |
| `main.go` | 신규 | Go MCP SDK 기반 `NewServer`, `search_skills`/`load_skill` 툴, CLI 분기. Python에는 대응물 없음 |
| `snapshot.go` | 신규 | gob 직렬화 + 4계층 무효화 (roots hash → dir fingerprint → 개별 mtime → per-file checksum). Python에 없음 |
| `mcp_test.go` | 신규 | `mcp.NewInMemoryTransports` 기반 풀 MCP 계약 통합 테스트 |
| `stdio_test.go` | 신규 | 실제 `os/exec` 서브프로세스 MCP stdio 라운드트립 |
| `integration_test.go` | 신규 | `search→load→verify` Codex 패턴 통합 테스트 |
| `parity_test.go` | 신규 | frozen Python fixture 대조 (10/10 catalog, 10/10 load, 10/10 search) |
| `bench_test.go` | 신규 | cold/warm 반복 가능 기준 벤치마크 |
| `search_test.go` | 신규 | 8레이어 개별 레이어 + 직렬화 + 한국어 토큰 테스트 |
| `loader_test.go` | 신규 | 로드, 누락, 중복, 경로 탈출, 캐시 무효화 테스트 |

**총 14개 파일**: 재작성 5 (Python 로직 재구현), 신규 9 (MCP·테스트·스냅샷). 폐기 없음.

종료 증거: 결정 기록, 코드 자산 감사표, 깨끗한 기준 커밋.

### Gate 1 — 계약과 테스트 자료

- [x] `search_skills` 입력·출력·오류 스키마를 확정한다.
- [x] `load_skill` 입력·출력·오류 스키마를 확정한다.
- [x] `catalog_revision` 계산과 변경 규칙을 확정한다.
- [x] 신뢰 루트와 논리 이름 해석 규칙을 확정한다.
- [x] 정상, 무관 검색, 중복 이름, 루트 이탈, 심볼릭 링크 이탈,
  파일 변경·삭제를 포함한 로컬 테스트 fixture를 만든다.
- [x] Python 기준 구현을 사용할 경우 고정 fixture와 비교 명령을 기록한다.
- [x] 실제 카탈로그 수는 fixture가 고정되기 전까지 목표 수치로 단정하지 않는다.

종료 증거: 스키마 문서와 실패하는 인수 테스트가 함께 존재한다.

**현재 증거**: `docs/MCP_CONTRACT.md` (입출력·오류 스키마, `catalog_revision`, 신뢰 루트·논리 이름 해석 규칙), `mcp_test.go` (프로토콜 검증), `search_test.go`·`loader_test.go`·`parity_test.go` (정상·중복·탈출·변경·무관 검색·Python parity), `snapshot_test.go` (파일 변경·삭제)

### Gate 2 — 안전한 카탈로그 코어

- [x] 설정된 루트에서만 `SKILL.md`를 탐색한다.
- [x] frontmatter를 검증하고 안정된 메타데이터로 변환한다.
- [x] 중복 논리 이름을 거부한다.
- [x] 경로 순회와 루트 밖 심볼릭 링크를 거부한다.
- [x] 파일 내용을 읽은 현재 바이트 기준 SHA-256을 반환한다.
- [x] 파일 변경·삭제 시 오래된 캐시 결과를 반환하지 않는다.
- [x] 내부 오류에서 절대 경로와 운영체제 원문 오류를 제거한다.

종료 증거: 안전성·변경·삭제 테스트, race 테스트, 독립 코드 검토.

### Gate 3 — 제한된 검색

- [x] 검색 정규화와 점수 규칙을 문서화한다.
- [x] 점수가 0인 무관 결과를 제외한다.
- [x] 동일 입력에 항상 같은 순서를 반환한다.
- [x] 최대 결과 수를 강제한다.
- [x] 빈 질의와 결과 없음 동작을 계약과 일치시킨다.
- [x] 고정 질의 fixture로 순위 회귀 테스트를 만든다.

종료 증거: 관련성·무관 결과·순서·제한 회귀 테스트.

### Gate 4 — MCP와 운영자 CLI

- [x] stdio MCP에 `search_skills`, `load_skill`만 노출한다.
- [x] 성공 응답에 구조화 결과와 `catalog_revision`을 포함한다.
- [x] 실패 응답에 안정된 `code`, `message`, `retryable`을 포함한다.
- [x] MCP 오류 응답을 프로토콜 수준 통합 테스트로 검증한다.
- [x] `list --json`, `doctor --json`을 구현한다.
- [x] `help`, `--help`, `-h`가 유용한 설명과 종료 코드 0을 반환하게 한다.
- [x] 진단 출력에서 신뢰 루트의 절대 경로를 제거한다.

종료 증거: in-memory MCP 테스트, stdio 스모크 테스트, CLI 종료 코드 테스트.

### Gate 5 — 전체 검증과 Codex 통합

- [x] `gofmt` 결과가 깨끗하다.
- [x] `go test ./...`가 통과한다.
- [x] `go test -race ./...`가 통과한다.
- [x] `go vet ./...`가 통과한다.
- [x] `go build ./...`가 통과한다.
- [x] 저장소 밖 임시 디렉터리에서 바이너리 스모크 테스트를 실행한다.
- [x] Codex가 검색 후 정확히 한 스킬의 전체 문서를 반환받고, 마지막 지시문을
  정확히 추출하는지 고정 통합 작업으로 검증한다.
- [x] 다른 AI가 같은 integration 커밋에서 검증 명령을 독립 재실행한다.

종료 증거: 정확한 명령, 종료 코드, 테스트 수, 대상 커밋이
`HANDOFF.md`에 기록된다.

### Gate 6 — 제품 근거

- [x] eager 등록과 SkillLoader를 같은 모델·작업·카탈로그 조건에서 비교한다.
- [x] 카탈로그 오버헤드, 라우팅 작업 오버헤드, 총 입력 토큰을 분리한다.
- [x] top-1, top-5, 오로드, 미로드 지표를 보고한다.
- [x] synthetic fixture에서 cold·warm 검색과 로드의 p50·p95를 재현 가능한 방식으로 측정한다.
- [ ] 원시 입력과 기계 판독 결과를 커밋한다. 현재 작업 트리에만 기록되어
  있으며, 결과를 커밋할 때 이 항목과 저장소의 `uncommitted` 상태 표기도
  같은 커밋에서 갱신한다.
- [x] 공개 문구는 실제 측정 결과를 넘지 않는다.

종료 증거: `docs/BENCHMARK.md`와 커밋된 결과 자료만으로 수치를 재현한다.

**현재 증거**: Codex CLI `0.144.6`, `gpt-5.6-sol`, 10-skill 합성
카탈로그, 12개 태스크를 격리된 eager/MCP 환경에서 각 1회 실행했다. routing
scoring-only fixture oracle 1건을 교정한 뒤 fixture 성공은 eager 10/12,
SkillLoader 11/12였고, SkillLoader raw search
top-1은 8/10, top-5 recall은 9/10이었다. 작은 카탈로그에서 SkillLoader의
client-reported total input은 eager보다 242.84% 증가했다. 태스크 완수 품질,
반복 실행 통계, 실제 대형 카탈로그
break-even은 검증하지 않았다. 원시 자료와 재채점 명령은
`bench/results/2026-07-21-codex-0.144.6-gate6-isolated/` 및
`docs/PRODUCT_EVIDENCE.md`에 있다.

### Gate 7 — 공개 릴리스

- [x] 지원 플랫폼별 재현 가능한 빌드를 만든다.
- [x] 설치, 설정, 업그레이드, 롤백을 문서화한다.
- [ ] 릴리스 산출물로 clean-room 설치와 Codex 통합을 재검증한다.
- [ ] 보안 제보 절차와 실제 검증된 호환성 표를 공개한다.

종료 증거: 새 환경에서 소스 트리 없이 설치와 고정 워크플로를 완료한다.

**현재 증거**: `scripts/build.sh` (재현 빌드), `INSTALL.md` (설치·설정·제거), `docs/MCP_CONTRACT.md` (MCP 도구 스키마)

**릴리스 체크리스트** (v0.2.0):
- [ ] `git tag v0.2.0` + push
- [ ] `./scripts/build.sh v0.2.0` 실행, `dist/skillloader` 무결성 확인
- [ ] `go install github.com/voodoosim/skillloader@v0.2.0` fresh 머신 검증
- [ ] GitHub 릴리스 페이지에 binary + 체크섬 게시
- [ ] `go doc github.com/voodoosim/skillloader` 링크 동작 확인

## 6. 다음 작업 묶음

다음 순서로 현재 프로토타입을 독립 프로젝트 기준에 맞춘다.

1. [x] 기존 Go 파일의 재사용 판단표를 완성한다.
2. [x] 중복 이름 처리 구현을 문서의 거부 정책과 다시 일치시킨다.
3. [x] Python parity fixture와 허용 기준을 고정한다.
4. [x] 저장소 밖 stdio 스모크와 live Codex 통합을 검증한다.
5. [ ] live Claude Code와 OpenCode 통합을 검증한다.
6. [x] synthetic cold/warm benchmark로 캐시와 검색 가중치를 평가한다.
7. [ ] 검증 결과를 커밋하고 해당 커밋을 독립 AI가 다시 검토한다.

## 7. 중단 조건

다음 조건에서는 범위를 늘리지 않고 해당 Gate로 돌아간다.

- 호출자가 임의 경로를 지정할 수 있다.
- 심볼릭 링크 이탈을 재현 테스트로 차단하지 못한다.
- 계약과 실제 MCP 구조화 응답이 다르다.
- 기존 코드의 존재만으로 완료 표시가 생긴다.
- benchmark가 카탈로그 절감과 전체 토큰 절감을 분리하지 못한다.
- Codex 통합 전에 HTTP, Docker, 두 번째 클라이언트가 범위에 추가된다.

## 8. 결정 및 미결정 사항

| 결정 | 필요한 시점 | 현재 상태 |
|---|---|---|
| GitHub 소유자와 Go 모듈 경로 | Gate 0 | `voodoosim`, `github.com/voodoosim/skillloader` |
| 라이선스 | Gate 0 | MIT |
| Go 버전과 환경 | Gate 0 | `go 1.26.5`; 동일 버전의 암묵적 toolchain과 `GOTOOLCHAIN=auto` 사용 |
| MCP SDK | Gate 0 | 공식 Go SDK `v1.6.1`; 알려진 `v1.2.0` 경보 제거 |
| 기존 Go 코드 재사용 범위 | Gate 0 | 감사 완료: 14개 파일 중 재작성 5, 신규 9 (Gate 0 감사표 참고) |
| 카탈로그 root 설정 형식 | Gate 1 | 쉼표 구분 literal path; 상대경로는 cwd 기준 |
| 검색 최대 결과 수 | Gate 1 | 요청 1~10, 범위 밖·생략 시 5 |
| tags 없는 스킬 | Gate 1 | 허용하되 doctor warning |
| YAML frontmatter 없는 legacy 문서 | Gate 1 | MVP에서 거부 |
| 검색 토큰 문자 범위 | Gate 1 | 영문·숫자·한글·하이픈 |
| 실행 중 카탈로그 변경 감지 | Gate 2 | 재시작 필요; hot reload 미구현 |
| Python 기준 구현과 fixture 위치 | Gate 1 | `scripts/verify_parity.py`, `testdata/parity/` (10/10 통과) |
| 캐시 용량과 eviction | Gate 6 | 측정 후 결정 |
| 두 번째 MCP 클라이언트 | Gate 7 이후 | Codex CLI `0.144.6` fixture 검증 완료; OpenCode·Claude Code 미검증 |
