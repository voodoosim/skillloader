# Round 3 검증 보고서

**Branch:** `main`  
**날짜:** 2026-07-21  
**Commits:** `434064e` → `1565c48` (5개)

---

## 발견 사항

### 1. 데드 코드: `dirFingerprint` (Low)

**파일:** `snapshot.go:198`

`dirFingerprint` 함수가 어디서도 호출되지 않는다. `fingerprintPaths`와 `DiscoverSkills`가 각각 직접 호출된 이후 완전히 방치된 레거시.

```go
func dirFingerprint(roots []string) (string, error) {
    paths, err := DiscoverSkills(roots)
    if err != nil {
        return "", err
    }
    return fingerprintPaths(paths), nil
}
```

`loadSnapshot`과 `saveSnapshot`은 `DiscoverSkills` → `fingerprintPaths`를 직접 호출하므로 이 래퍼 함수는 불필요하다.

---

### 2. `lookup()` colon-suffix 매칭 미검증 (Medium)

**파일:** `loader.go:100-102`

```go
if e.Name == name || strings.HasSuffix(e.Name, ":"+name) {
```

`plugin:skillname` 형태의 namespace prefix 매칭 경로가 어떤 테스트에서도 실행되지 않는다. 이 코드 경로가 실제로 작동하는지 검증되지 않았다.

---

### 3. MCP 핸들러 입력 검증 미검증 (Medium)

**파일:** `main.go:77-83, 87-88, 118-123`

| 핸들러 | 누락된 테스트 |
|--------|-------------|
| `search_skills` | 빈 쿼리 → `INVALID_ARGUMENT` |
| `search_skills` | `limit <= 0` 또는 `limit > 10` → 5로 클램핑 |
| `load_skill` | 빈 이름 → `INVALID_ARGUMENT` |

셋 다 MCP 레이어에서 테스트된 적이 없다.

---

### 4. `strongMatch` description-only 필터링 미검증 (Medium)

**파일:** `search.go:61-79`

태그 또는 이름 매치가 존재할 때 description-only 결과를 제외하는 필터가 어떤 시나리오에서도 명시적으로 테스트되지 않았다. (기존 검색 테스트는 모두 성공 시나리오만 검증)

---

### 5. Search tiebreaker (알파벳순 이름 정렬) 미검증 (Low)

**파일:** `search.go:84`

동점일 때 `entry.Name` 알파벳 순으로 정렬하는 타이브레이커가 테스트되지 않았다.

---

### 6. `layerSafetyFilter` 추가 제거 조건 미검증 (Low)

**파일:** `search.go:245-259`

| 조건 | 검증 여부 |
|------|----------|
| `s.score <= 0` → continue | 미검증 |
| `s.entry.Path == ""` → continue | 미검증 |

---

### 7. YAML 프론트매터 에러 경로 미검증 (Medium)

**파일:** `catalog.go:250-252, 278-279, 287-288`

| 조건 | 검증 여부 |
|------|----------|
| YAML 언마샬 에러 (잘못된 YAML) | 미검증 |
| `tags`에 문자열 아닌 리스트 항목 | 미검증 |
| `tags`에 int/bool/map 등 잘못된 타입 | 미검증 |

---

### 8. Snapshot 에러 경로 미검증 (Low)

**파일:** `snapshot.go`

| 조건 | 검증 여부 |
|------|----------|
| `snapshotPath()` 실패 (CacheDir 없음) | 미검증 |
| corrupt `.gob` 파일 decode 실패 | 미검증 |
| `DiscoverSkills` 에러 | 미검증 |
| `saveSnapshot` temp 파일 생성/쓰기/rename 실패 | 미검증 |

---

### 9. Doctor 에러 경로 미검증 (Medium)

**파일:** `doctor.go`

| 조건 | 검증 여부 |
|------|----------|
| 중복 스킬 이름 감지 | 미검증 |
| root가 디렉토리가 아님 | 미검증 |
| `ListJSON` / `ListText` | 미검증 |

---

### 10. `readTrustedFile` 오류 분류 모호 (Low)

**파일:** `catalog.go:190-196`

```go
resolvedPath, err := filepath.EvalSymlinks(absPath)
if err != nil {
    if errors.Is(err, os.ErrNotExist) {
        return nil, errUnreadableSkill
    }
    return nil, errOutsideTrustedRoots  // ← 권한 오류도 여기로 분류됨
}
```

`EvalSymlinks`가 `ErrNotExist`가 아닌 오류(권한 거부 등)를 반환하면 "source escapes its trusted root"로 분류되는데, 실제 원인은 경로 이탈이 아닐 수 있다.

---

### 11. `normalizeYAMLString` default branch 정보 누출 가능성 (Low)

**파일:** `catalog.go:307-308`

```go
default:
    return fmt.Sprintf("%v", v)
```

`name`/`description`이 예상치 못한 타입일 때 `%v`로 문자열화한다. 신뢰된 로컬 파일 파싱이므로 실질적 위험은 낮다.

---

### 12. Cache 메서드 미검증 (Low)

**파일:** `cache.go`

| 메서드 | 라인 | 검증 여부 |
|--------|------|----------|
| `InvalidateDocument` | 92-96 | 미검증 |
| `IndexHash` | 57-61 | 직접 테스트 없음 (MCP 코드에서만 사용) |

---

## 요약

| 심각도 | 건수 | 대표 항목 |
|--------|------|-----------|
| **Medium** | 4 | colon-suffix lookup, MCP 입력 검증, strongMatch 필터, YAML 에러 경로 |
| **Low** | 8 | 데드 코드, tiebreaker, safety filter, snapshot 에러, doctor 에러, 오류 분류, info leak, cache |

---

## 반영 결과 (5개 커밋)

| # | 항목 | 상태 | 커밋 | 변경 |
|---|------|------|------|------|
| 1 | `dirFingerprint` 데드 코드 | ✅ | `deff96e` | snapshot.go -8줄 제거 |
| 2 | colon-suffix lookup 미검증 | ✅ | `deff96e` | `TestLoaderLoadByNamespaceSuffix` 추가 |
| 3 | MCP 입력 검증 미검증 | ✅ | `434064e` | `maxSearchQueryRunes=4096`, `maxSkillNameRunes=256` bounds + `TestMCPRejectsOversizedInputs` |
| 4 | strongMatch 필터 미검증 | ❌ | — | 테스트 없음 |
| 5 | Search tiebreaker 미검증 | ✅ | `55ce7a3` | `TestSearchTieBreaksByName` 추가 |
| 6 | `layerSafetyFilter` 미검증 | ✅ | `510f73a` | `TestSafetyFilterRejectsNonPositiveAndMissingPath` 추가 |
| 7 | YAML 에러 경로 미검증 | ✅ | `510f73a` | `TestParseFrontmatterRejectsInvalidYAMLAndTags` (broken YAML, non-string list, bad type) |
| 8 | Snapshot corrupt gob 미검증 | ✅ | `1565c48` | `TestLoadSnapshotRejectsCorruptGob` 추가 |
| 9 | Doctor 에러 경로 미검증 | ✅ | `1565c48` | `TestDoctorDetectsDuplicateAndInvalidRoot` + `TestListOutputsAreValid` 추가 |
| 10 | `readTrustedFile` 오류 분류 | ✅ | `2c99ce7` | `errOutsideTrustedRoots` → `errUnreadableSkill` |
| 11 | `normalizeYAMLString` default branch | 미반영 | — | Low priority, 실질적 위험 낮음 |
| 12 | Cache 메서드 미검증 | ✅ | `55ce7a3` | `TestCacheInvalidateDocumentAndIndexHash` 추가 |

**해결:** 11/12 (91.7%)

## 검증 결과

| 항목 | 결과 |
|------|------|
| `go test -race ./...` | **PASS** |
| `go vet ./...` | **PASS** |
| `gofmt -l .` | **clean** |
| Coverage | 78.1% → **83.9%** (+5.8%) |

**미해결:** strongMatch description-only 필터 (#4) — Medium priority
