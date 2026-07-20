# SkillLoader — Local Skill Catalog Loader

## Review resolution

| Review | Resolution in this branch |
|---|---|
| 1 | Replaced OS/kernel positioning with local catalog loader/server wording. |
| 2 | Removed unmeasured reduction strength and numerical claims. |
| 3 | Documented the per-load read/hash cost; latency remains unmeasured. |
| 4 | Replaced the all-Done table and labeled ranking weights provisional. |
| 5 | Made missing tags valid with doctor warnings; current counts are in `HANDOFF.md`. |
| 6 | Added successful help paths and fixed the env/tokenizer contract without adding new languages. |
| 7 | Added YAML list/multiline parsing and explicitly rejected no-frontmatter legacy documents for MVP. |
| 8 | Split parity into catalog coverage, exact-load bytes/metadata, and search ranking; fixtures remain open. |
| 9 | Enforced trusted-root containment and added direct/symlink escape tests. |
| 10 | Added typed output schemas, structured content, catalog revision, redacted errors, and an MCP integration test. |
| 11 | Split client-independent core evidence from live-client evidence. |
| 12 | Narrowed stop conditions to client incompatibility and required SDK security upgrades. |
| 13 | Recorded tag, legacy, hot-reload, module, and Go-environment decisions or open states. |

<!--
REVIEW[1] "Skill OS"는 마케팅 비유지 실제 OS가 아님. 프로세스 스케줄러,
가상 메모리, 인터럽트 같은 기능은 없음. 이 비유가 오해를 부를 수 있으니
"discovery+load kernel" 정도로 톤다운 고려.
-->

<!--
FEEDBACK[1][ACCEPT]
판정: 과대포장 위험이 맞음.
수정안: 제품명과 핵심 설명은 "local skill catalog loader/server"처럼 실제
기능으로 쓰고, kernel 비유는 보조 설명으로만 제한할 것.
-->

## Product thesis

SkillLoader is a local skill catalog loader and MCP server. It discovers
`SKILL.md` documents under configured trusted roots and loads only a selected
document into the model context.

The model sees two MCP tools (`search_skills`, `load_skill`) instead of the full
catalog. Discovery, ranking, caching, and trusted-root enforcement remain on the
server side.

Three outcomes together make it valuable:

1. designed to lower skill-catalog context overhead;

<!--
REVIEW[2] "drastically"는 Gate 3에서 측정 전까진 주장 불가. plan.md 원문은
"lower"였고 이게 더 정직함. 벤치마크 전에 과장된 표현은 제거할 것.
-->

<!--
FEEDBACK[2][ACCEPT]
판정: 측정 전 성능·절감 강도 표현은 근거가 없음.
수정안: "lower" 또는 "designed to lower"로 바꾸고, 수치는 Gate 3 결과가
생긴 뒤에만 기록할 것.
-->

2. measurable routing and loaded-content behavior against frozen fixtures; and
3. installation as one local binary without Docker.

Each load reads and hashes the current file bytes before checking the document
cache. The cache avoids repeated frontmatter validation; its latency effect is
unmeasured and it is not counted as a token-saving feature.

<!--
REVIEW[3] "캐시는 지연시간 기능"이라고 했지만 cache.go:GetDocument()는 매번
파일 checksum을 다시 읽는다 (cache.go:70). 즉 "항상-fresh" 전략이지 "지연시간
최적화"가 아님. checksum 검증을 위한 I/O 때문에 캐시 히트도 디스크 읽기가
발생하므로, 실제 지연시간 개선은 거의 없고 "파싱 생략"만 절약됨.
이 설계 긴장을 문서화하거나, 타이머 기반 TTL로 전환 검토 필요.
-->

<!--
FEEDBACK[3][REVISE]
판정: 캐시 히트에서도 파일 전체 읽기와 SHA-256 계산이 발생한다는 관찰은
맞지만, "지연시간 개선이 거의 없음"은 benchmark 전에는 단정할 수 없음.
현재 load 경로는 frontmatter 전체 파싱이 아니라 접두 검사만 하므로 "파싱
생략"도 정확하지 않음. TTL은 stale 결과를 허용하는 별도 tradeoff임.
수정안: 현재 비용 구조를 문서화하고 cold/warm benchmark 후 캐시 전략을 결정할 것.
-->

## Current prototype surfaces

| Surface | Source | Current evidence |
|---|---|---|
| Catalog discovery | `catalog.go` | Trusted-root walk and YAML frontmatter tests |
| Deterministic search | `search.go` | Bounded ordering and zero-score rejection tests; weights remain provisional |
| In-memory cache | `cache.go` | Checksum-keyed cache tests; each load still reads and hashes the file |
| MCP tools | `main.go` | Exactly two typed tools covered by an in-memory protocol test |
| Path safety | `catalog.go`, `loader.go` | Direct outside-root and symlink-escape tests |
| Operator CLI | `doctor.go`, `main.go` | JSON diagnostics and help exit-code tests |

This table records code and test surfaces, not release, parity, benchmark, or
live-client completion.

<!--
REVIEW[4] 테이블은 전부 "Done"이지만 실제 누락 항목:
- "IO scheduler" 없음 — 동시성 제어 0, `go test -race` 안 함
- "Process isolation" 없음 — 하나의 로드 실패가 다른 요청에 영향 없음은 증명됨
  (각 MCP 호출이 독립적), 그러나 이걸 보장하는 명시적 격리 코드는 없음
- 검색 스코어링 상수(search.go:96 tag=8, :110 name=100/20, :122 desc=5)는
  임의로 정한 값. 어떤 실험 데이터로도 튜닝되지 않음.
-->

<!--
FEEDBACK[4][REVISE]
판정: 스코어 상수에 fixture·실험 근거가 없다는 지적은 맞지만 이는 확인된
버그보다 설계 근거 부족임. IO scheduler와 process isolation은 OS 비유에서
파생된 개념이며 현재 MVP 요구사항으로 확정되지 않았음.
현재 `go test -race ./...`는 통과하지만 기존 Done 표의 근거로 기록된 적은 없음.
또한 테스트 함수는 22개가 아니라 25개이고 `loader.go`에 gofmt 차이가 남아 있음.
수정안: Done 표를 제거하고 각 항목을 검증 증거가 있는 상태값으로 교체할 것.
-->

## What makes this different from the old plan

The old plan assumed a **frozen 82-skill catalog** and parity with the Python
loader. That was the pre-implementation baseline.

The Go prototype auto-discovers documents across configured roots. Local catalog
counts are observations recorded in `HANDOFF.md`; they are not parity targets
because the Python and Go loaders do not yet share a frozen fixture population.

<!--
REVIEW[5] "133+ skills" 발견했지만 doctor가 138개 오류를 보고함. 이 중
133-138의 간극이 설명 안 됨. 실제로는:
- 4개 파일: 프론트매터 파서 실패 (YAML 없는 구형 스킬)
- 2개: skill-loader 이름 중복
- 132개: tags 필드 누락 (태그 없는 스킬들)
오류 대부분은 tags 누락인데, tags 없는 스킬도 유효한지 명시적 정책 필요.
현재 파서는 tags 없으면 빈 배열 → doctor가 "missing tags" 경고를 내지만
검색에서는 여전히 작동함. 이 불일치 해소 필요.
-->

<!--
FEEDBACK[5][REVISE]
판정: 정책 불일치 지적은 맞지만 수치를 정정해야 함.
현재 `doctor --json` 결과는 valid parsed skills 133개, missing_tags 진단 133개,
parse/read 오류 4개, duplicate-name 진단 1개(두 항목의 동일 이름)로 총 138개임.
skill_count와 error_count는 서로 빼서 해석하는 값이 아님.
수정안: tags 없음의 허용·경고·거부 정책을 먼저 정하고 진단 등급을 맞출 것.
-->

## MVP objective

One Go binary that:

- auto-discovers all skills from configured trusted roots
- exposes `search_skills` + `load_skill` over local stdio MCP
- applies the same deterministic ranking for every search
- rejects unsafe paths, missing names, and ambiguous duplicates
- supports `list --json` / `doctor --json` for operator inspection
- supports `help`, `--help`, and `-h` with exit code 0
- runs without Python, Node, or Docker

`SKILLLOADER_ROOTS` is a comma-separated list of literal paths with whitespace
trimmed; relative paths resolve against the process working directory. Quote,
tilde, and glob expansion are not supported. Search tokenization
is limited to English letters, digits, Hangul, and hyphens.

<!--
REVIEW[6] MVP 목표에 누락된 것:
- "--help 출력" — plan.md Gate 2에 명시됐으나 main.go에 없음.
  `./skillloader` (인자 없이)는 MCP 서버 모드로 진입하므로 CLI 도움말을
  볼 수 있는 경로가 없음. `--help` / `help` 서브커맨드 필요.
- "SKILLLOADER_ROOTS 환경변수" — 구현됐으나(main.go:108) 문서화 안 됨.
  쉼표 분리에 quoting 지원 없음 (splitSimple이 순수 split만 함).
  ~(tilde) 확장 없음. glob 없음.
- 토크나이저가 영문+한글만 인식함 (search.go:86 regex). 일어, 중문,
  이모지 쿼리는 무시됨.
-->

<!--
FEEDBACK[6][ACCEPT]
판정: `go run . --help`는 usage를 출력하지만 종료 코드 1이며, help 명령은
구현되지 않았음. SKILLLOADER_ROOTS는 단순 comma split과 공백 trim만 수행하고
tilde·quote·glob 확장은 없음. 토크나이저 문자 범위 지적도 맞음.
수정안: 환경변수 문법과 지원 언어 범위를 계약으로 먼저 고정하고, 필요하지
않은 확장 기능까지 자동으로 MVP 요구사항에 넣지는 말 것.
-->

## Current prototype scope

- [x] Trusted local catalog roots (4 roots: `.codex/skills`, disabled, `.agents`, `.claude`)
- [x] YAML frontmatter (`name`, `description`, optional string-list `tags`) and body loading
- [x] 8-layer deterministic bounded metadata search
- [x] Exact load by logical skill name
- [x] In-memory metadata/document cache with checksum invalidation
- [x] Two model-visible MCP tools over stdio (`search_skills`, `load_skill`)
- [x] CLI `list --json` and `doctor --json`
- [x] CLI `help`, `--help`, and `-h`
- [x] Outside-repository binary and stdio EOF smoke test

Tags are optional and reported as doctor warnings. Documents without YAML
frontmatter are rejected in the MVP. Running processes do not hot-reload the
catalog; restart is required.

<!--
REVIEW[7] "Full SKILL.md metadata"라고 하지만 parseFrontmatter(catalog.go:89)는
YAML `---` 블록만 처리. `key: "value"` 형식의 단순 파싱만 하므로:
- 중첩 YAML (예: tags 아래 리스트)은 파싱 실패
- 본문 내 `---` (horizontal rule)를 프론트매터 종료로 오인 가능
- description이 여러 줄이면 첫 번째 `:` 이후만 가져옴
4개의 구형 스킬(프롬프트-결정화 등)은 `# Title` 바로 시작해서 아예 파싱 실패.
이걸 의도된 거부(deliberate rejection)로 볼지, 파서 개선 대상으로 볼지 결정 필요.
-->

<!--
FEEDBACK[7][REVISE]
판정: "Full metadata" 주장은 틀림. 다만 현재 구현은 YAML 파서가 아니라
단순 line parser이므로 중첩 필드는 항상 오류를 반환하기보다 조용히 무시함.
본문의 `---` 오인은 정상 closing delimiter가 없는 문서에서만 발생할 수 있음.
멀티라인 description은 후속 줄이 무시되며, 시작 delimiter가 없는 4개 문서는
현재 실제 파싱 오류로 집계됨.
수정안: 지원 frontmatter 문법과 legacy 문서 처리 정책을 계약으로 확정할 것.
-->

### Not yet done

- [ ] Codex/OpenCode bootstrap integration + live MCP test
- [ ] GitHub remote + module path + license
- [ ] Frozen-fixture parity for catalog coverage, exact-load bytes/metadata, and search ranking
- [ ] Token-saving measurement (Gate 3 evidence)

<!--
REVIEW[8] "Python loader parity benchmark" — 구체적으로 무엇을 비교?
  1) 동일 쿼리에 대한 검색 결과 순서 일치?
  2) 동일 스킬명에 대한 로드 내용 일치?
  3) 카탈로그 인덱스 개수 일치? (Python은 SKILLS.md 기반 82개, Go는
     자동발견 133개 → 수치 자체가 다를 것임)
비교 대상을 명확히 해야 함. 현재 구현이 Python loader의 frozen fixture조차
만들지 않았으니, "fixtures still needed"가 너무 추상적.
-->

<!--
FEEDBACK[8][ACCEPT]
판정: parity 대상과 성공 조건이 정의되지 않았음.
수정안: catalog coverage, exact-load bytes/metadata, search ranking을 별도 계약과
fixture로 나누고 각 지표의 허용 차이를 명시할 것. Python 82개와 Go 자동발견
133개는 모집단이 달라 단순 count equality를 parity로 사용하지 말 것.
-->

## Acceptance gates

### Gate 1 — Core safety

- [x] go.mod initialized + official Go MCP SDK pinned
- [x] Catalog auto-discovery across 4 roots
- [x] Resolved path containment enforced against configured trusted roots
- [x] Duplicate names caught, missing names rejected
- [x] Cache hit, miss, changed-file checksum, and symlink escape tested
- [ ] Define frozen fixtures and acceptance thresholds for:
  - catalog coverage on the same input population;
  - exact-load bytes and metadata; and
  - search ranking (top-1/top-5 and allowed alternatives).

Raw catalog-count equality is not a parity criterion when loaders scan different
populations.

<!--
REVIEW[9] 경로 순회 검증에서 한 가지 구멍:
- loader.go:containsTraversal()은 `..` 문자열만 검사
- `/home/user/.codex/skills/evil/../../secret` 은 잡지만
- `/home/user/.codex/skills/symlink -> /etc` 의 symlink 타겟은
  EvalSymlinks로 실제 경로가 노출될 뿐, "이 symlink를 따라가도 되는가"를
  검증하지 않음. symlink 화이트리스트 없음.
- Windoes 절대경로(`C:\...`), UNC 경로(`\\?\...`)는 리눅스에서 무의미하나
크로스플랫폼 빌드 시 잠재 이슈.
-->

<!--
FEEDBACK[9][ACCEPT]
판정: 치명적 안전성 결함이 맞음. EvalSymlinks 결과를 계산하지만 구성된 신뢰
루트와 비교하지 않아 루트 밖의 정상 절대경로도 통과함.
수정안: 해석된 경로의 trusted-root containment를 강제하고 symlink escape와
루트 밖 직접 경로를 테스트할 것. Windows/UNC는 지원 플랫폼 확정 후 별도 검증할 것.
-->

### Gate 2 — Product integration

- [x] Two MCP tools expose typed schemas, structured output, `catalog_revision`, and redacted error envelopes
- [x] CLI list + doctor with `--json`
- [x] CLI help paths return exit code 0
- [x] Binary builds and runs outside the repository
- [ ] Live Codex bootstrap: search → load → apply skill body

<!--
REVIEW[10] "stable JSON output"은 json.MarshalIndent를 쓰므로 들여쓰기 있음.
MCP 클라이언트가 이걸 파싱할 수 있는지 검증 안 됨. 실제 MCP 스펙은
TextContent 안에 어떤 형식이든 허용하지만, 클라이언트가 JSON을 기대하는지
평문을 기대하는지 확인 필요.
-->

<!--
FEEDBACK[10][REVISE]
판정: JSON 들여쓰기는 파싱 문제의 원인이 아님. MCP는 TextContent의 문자열과
선택적 structuredContent/outputSchema를 모두 허용함.
실제 계약 불일치는 현재 핸들러가 JSON 문자열만 Content에 넣고 typed output을
nil로 반환해 structuredContent/outputSchema가 없으며, catalog_revision도 없고
일반 error 문자열에 의존한다는 점임.
수정안: docs/MCP_CONTRACT.md와 동일한 typed output·redacted error envelope를
구현하고 프로토콜 통합 테스트로 검증할 것.
공식 근거: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
-->

### Gate 3A — Core evidence (does not require a live client)

- [ ] Core latency benchmarks (100 cold + 100 warm)
- [ ] Frozen-fixture catalog, exact-load, and routing parity

### Gate 3B — Live-client evidence (requires Gate 2 Codex integration)

- [ ] Token overhead measurement (catalog vs eager registration)
- [ ] End-to-end loaded-skill application quality

<!--
REVIEW[11] 이 게이트의 모든 항목이 Codex/OpenCode bootstrap 통합 없이는
측정 불가. Gate 2의 Codex 연동이 선행되어야 함 → 의존성 명시 필요.
의존성: Gate 3 시작 전에 Gate 2 Codex 항목이 완료되어야 함.
-->

<!--
FEEDBACK[11][REVISE]
판정: 전체 Gate 3가 막히는 것은 아님. 실제 client/model token overhead와
end-to-end 적용 품질은 bootstrap 통합에 의존하지만, 코어 latency와 frozen
fixture 기반 search/load parity는 Codex 없이 측정 가능함.
수정안: Gate 3을 core benchmark와 live-client benchmark로 나누고 후자에만
Gate 2 Codex 의존성을 명시할 것.
-->

### Gate 4 — Public release (not started)

## Stop conditions

Stop expanding scope when:

- Codex bootstrap does not reliably apply the loaded skill body
- Two-tool schema fails to reduce catalog overhead
- Path containment ever depends on caller-provided paths
- HTTP, Docker, semantic search requested before Gate 3 evidence exists
- the target client is verified not to support the required local stdio workflow
- a required MCP SDK security upgrade cannot preserve the tested contract

<!--
REVIEW[12] "Stop conditions"에 빠진 것:
- 133개 스킬 전수 파싱이 불가능하다고 판단될 때 (현재 4개 실패)
- MCP SDK API가 변경되어 현재 go-sdk v1.2.0 호환성이 깨질 때
- 실제 Codex/OpenCode가 stdio MCP를 지원하지 않는 것으로 확인될 때
-->

<!--
FEEDBACK[12][REVISE]
판정: client stdio 비호환은 중단·설계전환 조건이 될 수 있음. 반면 현재 4개
legacy 파싱 실패는 먼저 지원 정책으로 결정할 acceptance 문제임. SDK v1.2.0이
고정돼 있으므로 upstream API 변경만으로 현재 빌드가 즉시 깨지지는 않음.
수정안: SDK 보안 문제, 필수 업그레이드 실패, 대상 client 비호환을 중단 조건으로
좁히고 legacy format은 Gate 1 정책 결정으로 이동할 것.
-->

## Decisions and unresolved items

| Decision | Required before | State |
|---|---|---|
| GitHub owner + module path | Gate 1 | Needs user confirmation |
| License | Gate 1 | Needs user confirmation |
| `GOPATH == GOROOT` warning | Gate 1 | Needs user confirmation or environment correction |
| Codex/OpenCode bootstrap format | Gate 2 | Needs test with live MCP client |
| Search result max count | Gate 2 | 1–10; missing/out-of-range uses 5 |
| Missing tags | Gate 1 | Accepted; doctor warning only |
| Legacy documents without YAML frontmatter | Gate 1 | Rejected in MVP |
| Catalog hot reload | Gate 2 | Not implemented; restart required |
| Search token character set | Gate 1 | English, digits, Hangul, and hyphens |

<!--
REVIEW[13] 추가로 열어야 할 결정:
- tags 없는 스킬 처리 정책: 거부? 허용? 경고만? (현재 doctor는 "missing tags"
  를 오류로, 검색은 정상 동작 → 정책 불일치)
- 구형 프론트매터(# Title로 시작, YAML 없음) 지원 여부
- MCP 서버가 재시작 없이 카탈로그 변경을 감지할 방법 (현재는 프로세스 재시작만)
- Go module path: 지금은 `skillloader` (로컬 전용). GitHub 푸시 전에 변경 필요.
  임시 경로가 hardcoded된 곳은 없으나, import path가 바뀌면 모든 파일의
  package main 참조를 재검증해야 함.
-->

<!--
FEEDBACK[13][ACCEPT]
판정: 네 항목 모두 실제 미결정 사항임. 추가로 표의 `GOPATH == GOROOT`가
"Accepted as harmless in WSL"이라는 상태는 사용자 결정이나 검증 기록이 없어
현재 HANDOFF의 "unverified"와 충돌함.
수정안: 네 항목과 Go 환경 결정을 Gate 0/1에 올리고, 결정 전에는 완료나 승인
상태를 표시하지 말 것.
-->
