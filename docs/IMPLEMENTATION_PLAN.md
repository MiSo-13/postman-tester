# 단계별 개발 계획

## PR 1: 초기 앱 기반 (현재)

- [x] PyQt6 애플리케이션 시작 화면
- [x] 실행 위치의 `setting.json` 자동 생성·재로드
- [x] 실행 위치의 `data/app.db`에 프로젝트 / 실행 이력 / 보고서 인덱스 저장
- [x] Postman Collection v2.1 / Environment Import
- [x] Request/Response 예시 보기
- [x] 사람이 작성하거나 AI로 생성할 수 있는 예제 JSON 3종 다운로드
- [x] GET/HEAD/OPTIONS 중심의 보수적인 초기 HTTP 실행
- [x] HTML 및 Excel 결과 저장과 프로그램 재시작 후 조회
- [ ] 인증, JSON Body, Multipart, 단계 의존성은 후속 PR에서 구현

## 후속 PR

1. Request 편집기 및 사용자 설정 보존
2. USER/ADMIN 로그인, 비밀정보 저장소
3. JSONC, Query/Path/Header, Multipart 요청 빌더
4. 응답값 추출과 변수 바인딩
5. 시나리오/Revision 및 실행 회차 UI
6. 고급 성공·실패 판정과 실패 재실행
7. 결과 비교, 조치 내역, Excel 재가져오기
8. CI, Windows/Linux 패키징

## 실행 이력 보존 정책

`setting.json`은 앱 실행 위치에 있고, SQLite와 HTML/XLSX 보고서는 실행 위치의 `data/` 아래 저장합니다.
재실행 후에도 동일한 경로에서 열 수 있으며, 실행 기록은 새 Run ID로 분리됩니다.
`data/` 및 `setting.json`은 개인 데이터이므로 Git에 커밋하지 않습니다.

## 안전 정책

초기 Runner는 쓰기 Method를 기본적으로 실행하지 않습니다. 허용 설정이 있어도
Body/인증 요청은 현재 지원하지 않아 BLOCKED 처리합니다. API가 2xx를 반환하는지
확인하는 초기 smoke test이며 Postman JavaScript나 모든 비즈니스 검증은 지원하지 않습니다.
토큰이나 개인정보가 포함된 응답이 로그에 남을 수 있으므로 실제 서비스에서는 민감한 API 사용을 피하고
고급 마스킹 및 보안 저장 기능이 완성된 이후 사용하세요.
