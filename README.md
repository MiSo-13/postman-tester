# Postman Tester

Postman Collection/Environment를 Import하여 API를 확인하고 안전한 smoke test를 실행하는 PyQt6 데스크톱 도구입니다.

> 단계별 개발 중입니다. Raw JSON Body 전송은 후속 PR #3에서 지원하지만 USER/ADMIN 인증, multipart, Postman JavaScript 실행은 아직 미지원입니다. 쓰기 API는 기본적으로 건너뜁니다.

## 시작

Python 3.11 이상을 권장합니다.

```bash
git clone https://github.com/MiSo-13/postman-tester.git
cd postman-tester
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 주요 기능 (첫 PR)

- 프로젝트 생성 및 선택
- Postman Collection v2.1 / Environment JSON Import
- 중첩 API 폴더 탐색, Request/Response 예시 조회
- **예제 JSON 내려받기**: Postman Collection, Environment, setting 형식 3종
- 기본적인 읽기 API 테스트 (GET, HEAD, OPTIONS)
- 실행 결과 SQLite 저장, 실행별 HTML/XLSX 생성
- 이전 실행 및 보고서 경로 다시 조회

## 설정 및 데이터 보관

프로그램 최초 실행 시 시작 파일이 있는 폴더에 `setting.json`이 자동 생성됩니다.
PyInstaller 실행 파일은 실행 파일이 위치한 폴더를 사용합니다.
동일한 폴더에 `data/app.db` 및 `data/reports/<run-id>/`가 생성됩니다.
앱을 종료했다 다시 열어도 실행 기록 및 보고서 경로는 보존됩니다.

이 폴더에 쓰기 권한이 필요합니다. 비밀번호와 실제 토큰은 예제 JSON에 넣지 마세요.
테스트 대상은 Local 또는 격리된 개발 서버를 권장합니다.

## 예제 JSON을 AI로 생성할 때

앱의 **예제 JSON 내려받기** 버튼을 눌러 3개 파일을 받습니다.
AI에게 `postman_collection.example.json`을 주고
'Postman Collection v2.1 규격을 유지하여 내 API 목록의 method, URL, headers, body, response 예시를 채워줘'
라고 요청하면 됩니다.

## 개발

```bash
pytest -q
```

[단계별 개발 계획](docs/IMPLEMENTATION_PLAN.md)

## Raw JSON Body 실행 (PR #3)

1. 프로젝트에 Collection과 Environment를 가져옵니다.
2. API를 선택해 **JSON Body 편집** 탭에서 수정하고 **JSON 수정 저장**을 누릅니다.
3. 개발/테스트용 서버 주소와 데이터가 올바른지 검토합니다.
4. 쓰기 API 전송을 명시적으로 허용하려면 실행 폴더의 `setting.json`에서 `dangerous_methods_enabled`를 `true`로 변경한 후 앱을 재시작합니다.
5. 선택 API를 실행합니다. 실행 전 저장된 Body가 있으면 원본보다 우선 적용하고, JSONC 주석 제거와 변수 치환 후 `application/json`으로 전송합니다.

**주의:** 이 설정은 POST/PUT/PATCH/DELETE 요청 전송도 허용하므로 격리된 테스트 환경에서만 사용하세요.
인증, multipart 및 사용자 정의 JavaScript 처리는 지원하지 않으며, 관련 요청은 차단됩니다.
편집 내용을 저장하지 않으면 실행하지 않도록 UI에서 경고합니다. JSON Body는 현재 응답 검증 규칙이 아니라 HTTP 2xx로 성공 여부를 판정합니다.
