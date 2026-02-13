# 설정 및 경로 변경 가이드

이 문서는 프로젝트의 주요 경로와 설정을 변경하는 방법을 설명합니다.

## 1. 데이터베이스 경로 변경 (app.db)

### 현재 기본 경로
```
data/app.db
```

### 변경 방법

#### Option 1: 환경변수로 변경 (.env 파일)
```bash
# .env 파일 수정
DATABASE_URL=sqlite:///./data/app.db                    # 기본값
DATABASE_URL=sqlite:///./custom_path/my_database.db     # 사용자 정의 경로
DATABASE_URL=sqlite:////absolute/path/to/database.db    # 절대 경로
DATABASE_URL=postgresql://user:pass@localhost/dbname    # PostgreSQL
```

#### Option 2: config.py에서 기본값 변경
**파일**: `app/config.py`

```python
class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./data/app.db"  # 이 부분 수정
```

변경 예시:
```python
database_url: str = "sqlite:///./my_custom_db/app.db"
```

### 주의사항
- SQLite 경로 변경 시 디렉토리가 존재해야 함
- 경로 형식:
  - 상대 경로: `sqlite:///./path/to/db.db` (프로젝트 루트 기준)
  - 절대 경로: `sqlite:////absolute/path/to/db.db` (슬래시 4개)
- 데이터베이스 초기화: `python init_db.py`

---

## 2. 이미지 저장 경로 변경 (images/)

### 현재 기본 경로
```
images/
```

### 변경 방법

#### Step 1: confluence_parser.py 수정
**파일**: `app/services/confluence_parser.py`

**현재 코드 (20번째 줄 근처):**
```python
# Images directory
IMAGES_DIR = Path("images")
```

**변경 예시:**
```python
# Images directory
IMAGES_DIR = Path("my_custom_images")              # 상대 경로
IMAGES_DIR = Path("/absolute/path/to/images")      # 절대 경로
IMAGES_DIR = Path("static/uploaded_images")        # static 하위
```

#### Step 2: main.py에서 Static Files 경로 수정
**파일**: `app/main.py`

**현재 코드 (34-35번째 줄 근처):**
```python
# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")
```

**변경 예시:**
```python
# 이미지 경로를 my_custom_images로 변경한 경우
app.mount("/images", StaticFiles(directory="my_custom_images"), name="images")

# URL도 변경하고 싶은 경우 (예: /uploads로 접근)
app.mount("/uploads", StaticFiles(directory="my_custom_images"), name="images")
```

#### Step 3: .gitignore 업데이트 (선택)
**파일**: `.gitignore`

```bash
# Downloaded images from Confluence
images/                    # 기존
my_custom_images/          # 새 경로 추가
```

### 이미지 URL 접근 방식
- 기본: `http://localhost:8000/images/uuid.png`
- URL 변경 시: `http://localhost:8000/uploads/uuid.png`
- DB에는 `/images/uuid.png` 형식으로 저장됨 (main.py의 mount 경로와 일치)

### 주의사항
- 디렉토리가 존재하지 않으면 자동 생성됨 (mkdir_p=True)
- 상대 경로는 프로젝트 루트 기준
- 절대 경로 사용 시 권한 확인 필요
- 경로 변경 후 기존 이미지는 수동으로 이동 필요

---

## 3. 환경변수로 이미지 경로 관리 (권장)

더 유연한 관리를 위해 환경변수로 설정하는 방법:

### Step 1: config.py에 설정 추가
**파일**: `app/config.py`

```python
class Settings(BaseSettings):
    # ... 기존 설정 ...

    # Images
    images_directory: str = "images"  # 추가
```

### Step 2: confluence_parser.py 수정
**파일**: `app/services/confluence_parser.py`

```python
from app.config import settings

# Images directory
IMAGES_DIR = Path(settings.images_directory)
```

### Step 3: main.py 수정
**파일**: `app/main.py`

```python
from app.config import settings

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/images", StaticFiles(directory=settings.images_directory), name="images")
```

### Step 4: .env 파일에서 관리
**파일**: `.env`

```bash
# Images
IMAGES_DIRECTORY=images                        # 기본값
IMAGES_DIRECTORY=custom_images                 # 사용자 정의
IMAGES_DIRECTORY=/mnt/nfs/shared/images       # 네트워크 스토리지
```

---

## 4. 빠른 참조

| 항목 | 기본값 | 변경 파일 | 환경변수 |
|------|--------|-----------|----------|
| 데이터베이스 | `data/app.db` | `app/config.py` 또는 `.env` | `DATABASE_URL` |
| 이미지 저장 | `images/` | `app/services/confluence_parser.py`<br>`app/main.py` | (현재 없음, 위 3번 참고) |
| Static 파일 | `app/static/` | `app/main.py` | - |

---

## 5. 재시작 필요 여부

| 변경 사항 | 재시작 필요 |
|-----------|------------|
| .env 파일 수정 | ✅ 필요 |
| config.py 수정 | ✅ 필요 |
| confluence_parser.py 수정 | ✅ 필요 |
| main.py 수정 | ✅ 필요 |

**재시작 명령:**
```bash
# 개발 서버 재시작
Ctrl+C로 중단 후
uvicorn app.main:app --reload
```

---

## 6. 예제: 모든 데이터를 /data 폴더에 저장

```bash
# .env
DATABASE_URL=sqlite:///./data/app.db
IMAGES_DIRECTORY=data/images
```

```python
# app/main.py
app.mount("/images", StaticFiles(directory="data/images"), name="images")
```

디렉토리 구조:
```
project/
├── data/
│   ├── app.db           # 데이터베이스
│   └── images/          # 이미지
│       ├── uuid1.png
│       └── uuid2.jpg
├── app/
└── ...
```

---

## 7. 트러블슈팅

### 데이터베이스 파일을 찾을 수 없음
```bash
# 에러: sqlite3.OperationalError: unable to open database file

# 해결:
1. 경로의 디렉토리가 존재하는지 확인
mkdir -p data

2. 권한 확인
chmod 755 data

3. 절대 경로 사용 시 슬래시 개수 확인
sqlite:////absolute/path  (슬래시 4개)
```

### 이미지가 표시되지 않음
```bash
# 에러: 404 Not Found for /images/uuid.png

# 해결:
1. confluence_parser.py의 IMAGES_DIR과 main.py의 mount 경로 일치 확인
2. 디렉토리 존재 확인
3. 서버 재시작
4. 브라우저 캐시 클리어
```

### 환경변수가 적용되지 않음
```bash
# 해결:
1. .env 파일이 프로젝트 루트에 있는지 확인
2. 서버 재시작
3. 환경변수 로드 확인:
   python -c "from app.config import settings; print(settings.database_url)"
```

---

**마지막 업데이트**: 2026-02-03
**작성자**: Claude Sonnet 4.5
