# Postman Tester

Postman Collection v2.1과 Postman Environment JSON을 가져와 API를 탐색하고 테스트하는 **PyQt6 데스크톱 앱**입니다. 일반 수동 테스트와 선택형 OpenAI AI 테스트 계획·재계획 기능을 제공합니다.

## 설치 및 실행

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

## 빠른 시작

1. 프로젝트를 생성합니다.
2. Postman Collection JSON과 Environment JSON을 각각 가져옵니다.
3. USER/ADMIN 인증 프로필에서 Collection의 로그인 API, 계정, 토큰 응답 경로를 확인합니다.
4. 일반 실행 또는 **AI 테스트 계획**을 선택합니다.
5. AI 모드에서는 OpenAI API Key와 모델을 입력하고 생성된 계획을 검토합니다.
6. 실행 승인 후 결과·보고서를 확인합니다.

Environment의 `baseUrl`은 현재 실행할 개발·테스트 서버로 지정해야 합니다. Collection의 `{{userAccessToken}}`, `{{adminAccessToken}}`은 로그인 후 획득한 토큰으로 대체됩니다. 계정 암호와 토큰은 앱 데이터베이스에 저장하지 않습니다. 업로드할 때 Environment의 비밀값은 제거됩니다.

## 현재 지원 범위

- Collection 폴더/Endpoint 탐색과 요청·응답 예시 확인
- 일반 API 실행, JSONC Raw JSON Body, multipart form-data, 변수 추출 및 응답 검증
- USER/ADMIN 로그인 및 Refresh Token 처리
- 실행 시나리오, 재시도, 결과 이력, 보고서·대시보드·비교
- AI 테스트 계획: OpenAI Responses API 기반 실행 순서 제안, 사용자 검토 및 실행
- AI 재계획: 실패 시 이미 승인한 남은 API 중 다음 순서를 선택하거나 중단 (최대 0~3회)
- AI 입력·출력·캐시·추론 토큰 사용량 표시

**제한 사항:** AI가 새 API를 생성하거나 요청 Body·검증 규칙을 임의로 수정하지는 않습니다. Postman JavaScript 스크립트는 실행하지 않습니다. AI가 제안한 순서도 테스트 의존성과 필요한 입력값을 보장하지 않습니다.

## 쓰기 API와 보안

기본 설정은 읽기 요청(GET, HEAD, OPTIONS)만 실행합니다. POST/PUT/PATCH/DELETE를 실행하려면 `setting.json`의 `dangerous_methods_enabled`를 `true`로 변경하고 앱을 재시작하세요. 이 설정은 실제 서버 데이터를 변경할 수 있으므로 격리된 환경에서 사용하세요.

AI API Key는 실행 시 입력하며 로컬 파일에 저장하지 않습니다. AI 계획 생성에는 API 메타데이터를, 재계획에는 일부 실행 상태를 보냅니다. 토큰 사용량은 요청/화면 범위의 측정치이며 계정 전체 청구 금액은 아닙니다.

## 설정 및 데이터

실행 위치에 `setting.json`이 생성되며, `data/app.db`에 프로젝트·실행 기록, `data/reports/`에 보고서가 저장됩니다. 쓰기 권한이 있는 폴더에서 실행하세요.

## 테스트

```bash
python -m pytest -q
```

자동 테스트는 HTTP 모킹을 사용하므로 실제 서비스 환경의 로그인, 네트워크, 인증 정책까지 보증하지 않습니다. Windows/Linux GUI 및 패키징 검증도 배포 전에 별도로 수행해야 합니다.

[개발 계획](docs/IMPLEMENTATION_PLAN.md)
