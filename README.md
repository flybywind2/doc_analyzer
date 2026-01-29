# AI 과제 지원서 평가 시스템

AI 도입 프로그램 지원서를 Confluence에서 수집하여 LLM 기반으로 자동 평가/분류하고, 심사위원이 웹에서 조회 및 평가할 수 있는 시스템입니다.

## 주요 기능

- **Confluence 연동**: 지원서 데이터 자동 수집 및 파싱
- **LLM 자동 평가**: 8개 평가 기준으로 자동 등급 산정 (S/A/B/C/D)
- **AI 기술 분류**: LLM, RAG, ML, DL, AI Agent 등 자동 분류
- **권한 기반 조회**: 사업부별 권한 관리
- **심사위원 평가**: 웹 기반 평가 입력
- **통계 대시보드**: 사업부별, 카테고리별 통계 시각화
- **CSV 내보내기**: 평가 결과 데이터 추출

## 기술 스택

- **Backend**: FastAPI, Python 3.11+
- **Database**: SQLite3, SQLAlchemy ORM
- **Frontend**: Jinja2 Templates, HTML/CSS/JavaScript
- **LLM**: LangChain + OpenAI 호환 API
- **HTML Parsing**: BeautifulSoup4, lxml
- **Authentication**: JWT (python-jose), bcrypt

## 프로젝트 구조

```
ai_application_evaluator/
├── app/
│   ├── main.py                  # FastAPI 진입점
│   ├── config.py                # 환경설정
│   ├── database.py              # SQLAlchemy 설정
│   ├── models/                  # DB 모델
│   ├── schemas/                 # Pydantic 스키마
│   ├── services/                # 비즈니스 로직
│   ├── routers/                 # API 라우터
│   ├── templates/               # Jinja2 HTML
│   └── static/                  # CSS, JavaScript
├── data/                        # SQLite DB
├── logs/                        # 로그 파일
├── requirements.txt
├── .env
└── README.md
```

## 설치 및 실행

### 1. 가상환경 생성 및 활성화

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열어서 실제 값으로 수정
```

**필수 설정 항목:**
- Confluence 연동 정보 (URL, 인증정보, Space Key, Parent Page ID)
- LLM API 정보 (Base URL, API Key, Credential Key, Model Name)
- SECRET_KEY (최소 32자 이상의 랜덤 문자열)

### 4. 애플리케이션 실행

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 웹 브라우저 접속

```
http://localhost:8000
```

**기본 관리자 계정:**
- Username: `admin`
- Password: `admin123!` (최초 로그인 시 비밀번호 변경 필수)

## 사용 방법

### 1. 최초 설정 (관리자)

1. 관리자 계정으로 로그인
2. 비밀번호 변경
3. 사업부 정보 등록 (`/admin/departments`)
4. 사용자 계정 생성 (`/admin/users`)
5. AI 카테고리 확인/수정 (`/admin/categories`)
6. 평가 기준 확인/수정 (`/admin/criteria`)

### 2. 데이터 수집 및 평가 (관리자)

1. Confluence 데이터 동기화 실행 (`/admin/sync`)
2. AI 자동 평가 실행 (`/evaluations/run-ai`)
3. 대시보드에서 결과 확인 (`/dashboard`)

### 3. 심사위원 평가

1. 심사위원 계정으로 로그인
2. 지원서 목록에서 본인 사업부 과제 확인 (`/applications`)
3. 지원서 상세 페이지에서 평가 입력 (`/applications/{id}`)
4. 통계 대시보드에서 현황 확인

### 4. 데이터 내보내기

- CSV 내보내기 기능으로 평가 결과 추출
- 관리자: 전체 데이터
- 심사위원: 본인 사업부 데이터

## 권한 체계

| 기능 | 관리자 | 심사위원 |
|------|--------|----------|
| 전체 지원서 조회 | ✅ | ❌ |
| 본인 사업부 지원서 조회 | ✅ | ✅ |
| 지원서 평가 | ✅ | ✅ |
| Confluence 동기화 | ✅ | ❌ |
| AI 재평가 실행 | ✅ | ❌ |
| 사용자/사업부/카테고리 관리 | ✅ | ❌ |
| CSV 내보내기 | ✅ | ✅ (본인 사업부) |

## 평가 기준 (8개 항목)

1. **경영성과**: 비용 절감, 시간 단축 등 정량적 효과
2. **전략과제 유사도**: 회사 전략 방향과 일치도
3. **확장가능성**: 타 부서 적용, 기술적 확장
4. **참여자 역량**: 필요 기술 보유 여부
5. **실현가능성**: 현재 조건으로 구현 가능 여부
6. **Pain Point 명확성**: 문제 정의 구체성
7. **데이터 준비도**: 필요 데이터 확보 상태
8. **ROI 측정 가능성**: 효과 정량 측정 가능 여부

## AI 기술 카테고리

- **LLM**: 텍스트 생성, 요약, 번역, 챗봇
- **RAG**: 문서 검색, 지식베이스, Q&A
- **ML**: 예측, 분류, 회귀, 이상탐지
- **DL**: 이미지, OCR, 음성인식, 객체탐지
- **AI Agent**: 자동화, 워크플로우, 멀티스텝
- **데이터분석**: 인사이트, 시각화, BI

## 주요 API 엔드포인트

### 인증
- `POST /auth/login` - 로그인
- `POST /auth/logout` - 로그아웃
- `POST /auth/change-password` - 비밀번호 변경

### 지원서
- `GET /applications` - 목록 조회
- `GET /applications/{id}` - 상세 조회
- `POST /applications/sync` - Confluence 동기화
- `POST /applications/{id}/evaluate` - 사용자 평가 저장
- `GET /applications/export/csv` - CSV 내보내기

### 평가
- `POST /evaluations/run-ai` - AI 일괄 평가
- `POST /evaluations/{app_id}/re-evaluate` - AI 재평가
- `GET /evaluations/{app_id}/history` - 평가 이력

### 관리
- `GET/POST/PUT/DELETE /users` - 사용자 관리
- `GET/POST/PUT/DELETE /departments` - 사업부 관리
- `GET/POST/PUT/DELETE /categories` - AI 카테고리 관리

### 통계
- `GET /statistics/summary` - 요약 통계
- `GET /statistics/by-department` - 사업부별 통계
- `GET /statistics/by-category` - 카테고리별 통계

## 문제 해결

### LLM API 연결 오류
- `.env` 파일의 LLM 설정 확인
- 네트워크 연결 및 API 엔드포인트 확인
- API Key 및 Credential Key 유효성 확인

### Confluence 연동 오류
- Confluence URL 및 인증 정보 확인
- Space Key 및 Parent Page ID 확인
- Rate Limit 확인 (동기화 시 sleep 적용)

### 데이터베이스 오류
- `data/` 디렉토리 쓰기 권한 확인
- SQLite 파일 손상 시 삭제 후 재실행

## 개발자 정보

- **Version**: 1.0.0
- **License**: Proprietary
- **Contact**: AI Team

## 라이선스

이 소프트웨어는 사내 전용으로 개발되었으며, 외부 배포를 금지합니다.
