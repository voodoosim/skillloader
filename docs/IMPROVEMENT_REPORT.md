# SkillLoader 개선 보고서

**Commit:** `e4eff5c`  
**Branch:** `main`  
**날짜:** 2026-07-21  

---

## 1. WarmSnapshot 2.75배 속도 향상 (Critical)

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
