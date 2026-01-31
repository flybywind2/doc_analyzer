"""
Initialize database with default data
"""
import bcrypt
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.category import AICategory
from app.models.evaluation import EvaluationCriteria


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def init_default_data(db: Session):
    """Initialize database with default data"""
    
    # Check if admin user already exists
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin_user = User(
            username="admin",
            password_hash=hash_password("admin123!"),
            name="시스템 관리자",
            role="admin",
            is_active=True,
            is_first_login=True
        )
        db.add(admin_user)
        print("✅ Default admin user created (username: admin, password: admin123!)")
    
    # Initialize AI Categories
    categories_data = [
        {"name": "LLM", "description": "텍스트 생성, 요약, 번역, 챗봇", 
         "keywords": '["텍스트 생성", "요약", "번역", "챗봇", "GPT", "NLP", "자연어처리", "언어모델", "생성형AI", "대화", "질의응답", "문서생성", "프롬프트"]', "display_order": 1},
        {"name": "RAG", "description": "문서 검색, 지식베이스, Q&A", 
         "keywords": '["문서 검색", "지식베이스", "Q&A", "벡터DB", "임베딩", "검색증강", "정보검색", "문서관리", "지식관리", "벡터", "유사도검색"]', "display_order": 2},
        {"name": "ML", "description": "예측, 분류, 회귀, 이상탐지", 
         "keywords": '["예측", "분류", "회귀", "이상탐지", "추천", "XGBoost", "머신러닝", "학습", "모델", "알고리즘", "패턴", "데이터분석", "분석모델"]', "display_order": 3},
        {"name": "DL", "description": "이미지, OCR, 음성인식, 객체탐지", 
         "keywords": '["이미지", "OCR", "음성인식", "객체탐지", "CNN", "딥러닝", "영상처리", "비전", "얼굴인식", "문자인식", "사진", "비디오"]', "display_order": 4},
        {"name": "AI Agent", "description": "자동화, 워크플로우, 멀티스텝", 
         "keywords": '["자동화", "워크플로우", "멀티스텝", "RPA", "에이전트", "자율", "프로세스자동화", "업무자동화", "지능형", "협업", "작업흐름"]', "display_order": 5},
        {"name": "데이터분석", "description": "인사이트, 시각화, BI", 
         "keywords": '["인사이트", "시각화", "BI", "대시보드", "분석", "통계", "리포트", "차트", "그래프", "데이터", "지표", "트렌드", "경향"]', "display_order": 6},
    ]
    
    existing_categories = db.query(AICategory).count()
    if existing_categories == 0:
        for cat_data in categories_data:
            category = AICategory(**cat_data)
            db.add(category)
        print(f"✅ {len(categories_data)} AI categories created")
    
    # Initialize Evaluation Criteria
    criteria_data = [
        {
            "name": "경영성과",
            "description": "비용 절감, 시간 단축 등 정량적 효과",
            "weight": 1.0,
            "evaluation_guide": "비용 절감, 시간 단축, 생산성 향상 등 정량적으로 측정 가능한 경영 성과를 평가합니다.",
            "display_order": 1
        },
        {
            "name": "전략과제 유사도",
            "description": "회사 전략 방향과 일치도",
            "weight": 1.0,
            "evaluation_guide": "회사의 전략 방향 및 중점 추진 과제와의 일치도를 평가합니다.",
            "display_order": 2
        },
        {
            "name": "확장가능성",
            "description": "타 부서 적용, 기술적 확장",
            "weight": 1.0,
            "evaluation_guide": "다른 부서나 업무로 확장 적용할 수 있는 가능성을 평가합니다.",
            "display_order": 3
        },
        {
            "name": "참여자 역량",
            "description": "필요 기술 보유 여부",
            "weight": 1.0,
            "evaluation_guide": "과제 수행에 필요한 기술적 역량을 참여자가 보유하고 있는지 평가합니다.",
            "display_order": 4
        },
        {
            "name": "실현가능성",
            "description": "현재 조건으로 구현 가능 여부",
            "weight": 1.0,
            "evaluation_guide": "현재의 기술, 자원, 환경으로 실제 구현이 가능한지 평가합니다.",
            "display_order": 5
        },
        {
            "name": "Pain Point 명확성",
            "description": "문제 정의 구체성",
            "weight": 1.0,
            "evaluation_guide": "해결하고자 하는 문제가 명확하고 구체적으로 정의되어 있는지 평가합니다.",
            "display_order": 6
        },
        {
            "name": "데이터 준비도",
            "description": "필요 데이터 확보 상태",
            "weight": 1.0,
            "evaluation_guide": "AI 모델 학습 및 운영에 필요한 데이터의 확보 상태를 평가합니다.",
            "display_order": 7
        },
        {
            "name": "ROI 측정 가능성",
            "description": "효과 정량 측정 가능 여부",
            "weight": 1.0,
            "evaluation_guide": "투자 대비 효과를 정량적으로 측정할 수 있는지 평가합니다.",
            "display_order": 8
        },
    ]
    
    existing_criteria = db.query(EvaluationCriteria).count()
    if existing_criteria == 0:
        for crit_data in criteria_data:
            criteria = EvaluationCriteria(**crit_data)
            db.add(criteria)
        print(f"✅ {len(criteria_data)} evaluation criteria created")
    
    db.commit()
    print("✅ Database initialization completed")
