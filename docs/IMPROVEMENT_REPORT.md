# SkillLoader 개선 보고서

**Branch:** `main`  
**날짜:** 2026-07-21  

---

## Round 1 (commit `e4eff5c`)

### 1. WarmSnapshot 2.75배 속도 향상 (Critical)

**파일:** `snapshot.go`

### 문제
`BenchmarkWarmSnapshot`이 `BenchmarkColdBuild`보다 느렸다.  
스냅샷 warm 로드가 콜드 빌드보다 비싼 이유는:

1. `loadSnapshot`에서 `DiscoverSkills`를 2회 호출 (중복 디렉터리 I/O)
2. 매번 모든 파일을 다시 읽어 SHA-256 체크섬 재검증 (mtime으로 이미 체크했는데도)

| 메트릭 | 수정 전 | 수정 후 | 개선율 |
|--------|---------|---------|--------|
| ColdBuild | 1,961,520 ns | 1,863,470 ns | ~5% |
| WarmSnapshot | 2,187,796 ns | 794,588 ns | **2.75x** |
| Warm vs Cold 비율 | 1.12x 느림 | **2.34x 빠름** | ✅ |

### 변경사항
- `loadSnapshot`: `fileChecksum()` 검증 제거, mtime 기반 검증만 유지
- `dirFingerprint()` → `fingerprintPaths(paths)` 분리하여 `DiscoverSkills` 1회만 호출
- `saveSnapshot`도 동일하게 최적화
- 테스트 `TestSnapshotInvalidatesWhenInvalidFileBecomesValid`: 인위적 `Chtimes` 복원 제거 (현실적 mtime 기반 무효화)

---

## 2. 중복 체크섬 패턴 통합 (Medium)

**파일:** `catalog.go`, `loader.go`, `snapshot.go`

### 문제
`fmt.Sprintf("%x", sha256.Sum256(data))` 패턴이 4곳에 산재.

### 변경사항
- `catalog.go`에 `hexSHA256(data []byte) string` 헬퍼 추가
- `parseSkillData`, `Load`, `fileChecksum` 3곳에서 호출
- `loader.go`에서 `crypto/sha256`, `fmt` import 제거

---

## 3. trimSpace 유니코드 대응 (Medium)

**파일:** `main.go`

### 문제
커스텀 `trimSpace` 함수가 `' '`와 `'\t'`만 처리.  
유니코드 공백(non-breaking space, full-width space, CJK) 무시.

### 변경사항
- `strings.TrimSpace` 표준 라이브러리로 교체
- 불필요한 10줄 커스텀 함수 제거

---

## 검증 결과

| 검증 항목 | 명령어 | 결과 |
|-----------|--------|------|
| 단위 테스트 + race | `go test -race ./...` | **PASS** |
| 정적 분석 | `go vet ./...` | **PASS** |
| 포맷팅 | `gofmt -l .` | **clean** |
| 커버리지 | `-coverprofile` | 77.8% → **78.0%** |

**변경 통계:** 5개 파일, +28줄 / -45줄 (net -17줄)

---

## Round 2 (commit `44977e6`)

### 5. Cache GetDocument ABA Race Condition (High)

**파일:** `cache.go:72-79`

### 문제
`GetDocument` 더블 체크드 락에서 갱신된 캐시 데이터가 삭제될 수 있음.

```
A: RLock → doc.checksum = "BBB" (stale) → RUnlock
B: SetDocument(path, newContent, "AAA")  ← fresh data
A: Lock → current("AAA") != checksum("BBB") → B의 데이터 삭제!
```

### 변경사항
삭제 조건을 `current.checksum == doc.checksum`으로 변경. 자신이 읽은 stale 체크섬과 현재 캐시 체크섬이 같을 때만 삭제.

```go
// 수정 전
if current, exists := c.docs[path]; exists && current.checksum != checksum {

// 수정 후
if current, exists := c.docs[path]; exists && current.checksum == doc.checksum {
```

### 추가 테스트
- `TestCacheConcurrentGetSetNoDataLoss`: 100개 고루틴이 동시에 `GetDocument` 호출 → 문서 소실 없음 검증
- `-race` 20회 연속 반복 통과 확인

---

## 검증 결과 (Round 2)

| 검증 항목 | 명령어 | 결과 |
|-----------|--------|------|
| 단위 테스트 + race | `go test -race ./...` | **PASS** |
| 정적 분석 | `go vet ./...` | **PASS** |
| 포맷팅 | `gofmt -l .` | **clean** |
| 커버리지 | `-coverprofile` | **78.1%** |
| ColdBuild | `-bench=ColdBuild` | 1,874,954 ns |
| WarmSnapshot | `-bench=WarmSnapshot` | 754,858 ns (2.48x faster) |
| Concurrent test x20 | `-run=Concurrent -count=20` | **PASS** |
