# Postman Tester

Postman Collection/Environment를 Import하여 API를 확인하고 안전한 smoke test를 실행하는 PyQt6 데스크톱 도구입니다.

> 현재는 첫 개발 버전입니다. POST/PUT/PATCH/DELETE, 인증, JSON Body, multipart 및 Postman JavaScript 실행은 아직 완전 지원하지 않습니다. 쓰기 API는 기본적으로 건너뜁니다.

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
