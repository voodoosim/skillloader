# Gate 6 제품 근거

## 측정 가능성 판정

2026-07-21 현재 Codex CLI는 로그인 상태지만 Claude Code와 OpenCode에는
사용 가능한 provider 인증이 없다. 따라서 12개 태스크를 두 설정으로 모두
실행한 실측 결과를 생성하지 않았으며, 토큰 절감이나 작업 성공률을 주장하지
않는다.

확인 명령:

```bash
codex login status
claude auth status
opencode providers list
```

## 고정 비교 프로토콜

대상 fixture는 `bench/tasks/task-fixture-v1.json`이며 12개 태스크를 사용한다.
각 태스크를 같은 모델, 모델 버전, system instructions, temperature, 카탈로그,
작업 입력으로 두 번 실행한다.

### 설정 A — eager

10개 parity 스킬의 이름·태그·description·본문을 system prompt의 동일한
catalog section에 주입한다. 첫 모델 호출 전의 입력 토큰, 전체 입력 토큰,
최종 답변, 선택된 스킬을 원시 기록에 저장한다.

### 설정 B — SkillLoader

다음 루트로 MCP 서버를 시작한다.

```bash
SKILLLOADER_ROOTS="$PWD/testdata/parity/home/.codex/skills" go run .
```

초기 system prompt에는 MCP bootstrap과 도구 스키마만 넣고, 모델의
`search_skills` 호출과 선택된 `load_skill` 호출을 기록한다. 각 호출의
structured result, 입력 토큰, 최종 답변을 같은 원시 기록에 저장한다.

## 결과 형식

실측이 가능해지면 다음 파일을 `bench/results/<date>-<client>-gate6/`에 저장한다.

- `environment.json`: client/model/version, Go version, fixture SHA-256
- `tasks.jsonl`: 태스크 정의와 실행 순서
- `eager.jsonl`: eager 원시 호출·토큰·판정
- `skillloader.jsonl`: search/load 원시 호출·토큰·판정
- `summary.json`: top-1/top-5, no-load, incorrect-load, routing failure,
  catalog overhead, total input tokens, p50/p95

카탈로그 오버헤드와 총 입력 토큰 절감률은 분리 계산한다.

```text
reduction = 1 - (skillloader_tokens / eager_tokens)
```

클라이언트가 보고한 토큰 수가 없으면 tokenizer 이름·버전을 기록하고
`estimate`로 표시한다. 자격 증명, 사용자 데이터, 원문 비밀값은 저장하지 않는다.

## 현재 Gate 6 상태

- 합성 fixture의 Go cold/warm 성능 근거: 완료 (`bench/results/2026-07-20-go1.26.5-fixture100.json`)
- eager 대 SkillLoader 라이브 비교: 인증 부족으로 미실행
- 토큰·품질·라우팅 비교: 미측정
- 다음 재개 조건: Claude/OpenCode provider 인증 후 동일 프로토콜로 24회 실행
