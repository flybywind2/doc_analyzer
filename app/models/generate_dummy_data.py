"""
Generate dummy data for testing
"""
from datetime import datetime, timedelta
import random
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.department import Department
from app.models.application import Application
from app.models.evaluation import EvaluationHistory
from app.services.auth import get_password_hash


def generate_dummy_data(db: Session):
    """Generate dummy data for testing"""
    
    print("🔄 Generating dummy data...")
    
    # Check if dummy data already exists
    existing_apps = db.query(Application).count()
    if existing_apps > 0:
        print(f"⚠️  Dummy data already exists ({existing_apps} applications). Skipping...")
        return
    
    # Create departments
    departments_data = [
        {"name": "플랫폼개발팀", "total_employees": 50},
        {"name": "AI연구팀", "total_employees": 30},
        {"name": "데이터분석팀", "total_employees": 25},
        {"name": "서비스개발팀", "total_employees": 40},
        {"name": "인프라운영팀", "total_employees": 20},
    ]
    
    departments = []
    for dept_data in departments_data:
        dept = db.query(Department).filter(Department.name == dept_data["name"]).first()
        if not dept:
            dept = Department(**dept_data)
            db.add(dept)
            db.flush()
        departments.append(dept)
    
    db.commit()
    print(f"✅ Created {len(departments)} departments")
    
    # Create reviewers (one per department)
    reviewers = []
    for i, dept in enumerate(departments, 1):
        username = f"reviewer{i}"
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                password_hash=get_password_hash("password123!"),
                name=f"{dept.name} 심사위원",
                role="reviewer",
                department_id=dept.id,
                is_active=True,
                is_first_login=False
            )
            db.add(user)
            db.flush()
        reviewers.append(user)
    
    db.commit()
    print(f"✅ Created {len(reviewers)} reviewers")
    
    # Dummy application templates
    templates = [
        {
            "subject": "고객 상담 자동화 챗봇 구축",
            "current_work": "현재 고객 상담은 모두 수동으로 처리되고 있어 상담사 업무 부담이 큽니다.",
            "pain_point": "반복적인 질문에 대한 답변으로 상담사 시간의 70%가 소요되고, 야간/주말 대응이 어렵습니다.",
            "improvement_idea": "LLM 기반 챗봇을 구축하여 FAQ 자동 응답 및 1차 상담을 처리하고, 복잡한 문의만 상담사에게 전달합니다.",
            "expected_effect": "상담사 업무 시간 50% 절감, 24/7 고객 대응 가능, 고객 만족도 향상",
            "hope": "LLM 모델 선정 및 튜닝 지원, 챗봇 UI/UX 개발 지원",
            "ai_category": "LLM",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 3},
                {"category": "AI/ML", "skill": "LangChain", "level": 2}
            ]
        },
        {
            "subject": "사내 문서 검색 RAG 시스템 개발",
            "current_work": "사내 기술 문서가 여러 곳에 분산되어 있어 필요한 정보를 찾는데 많은 시간이 소요됩니다.",
            "pain_point": "문서 검색에 평균 30분 이상 소요, 검색 정확도 낮음, 업데이트된 정보 찾기 어려움",
            "improvement_idea": "RAG 시스템으로 Confluence, Wiki, 공유 드라이브의 문서를 통합 검색하고 질문에 대한 정확한 답변 제공",
            "expected_effect": "문서 검색 시간 80% 단축, 정보 접근성 향상, 업무 생산성 증대",
            "hope": "벡터 DB 구축 지원, 임베딩 모델 최적화 지원",
            "ai_category": "RAG",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 4},
                {"category": "데이터베이스", "skill": "Vector DB", "level": 2}
            ]
        },
        {
            "subject": "제품 수요 예측 모델 개발",
            "current_work": "현재는 과거 판매 데이터 기반의 단순 평균으로 수요를 예측하고 있습니다.",
            "pain_point": "계절성, 프로모션, 외부 요인 미반영으로 예측 정확도 60% 수준, 재고 부족 또는 과잉 발생",
            "improvement_idea": "ML 모델(XGBoost, LSTM)을 활용하여 다양한 변수를 고려한 수요 예측 시스템 구축",
            "expected_effect": "예측 정확도 85% 이상, 재고 비용 30% 절감, 품절률 50% 감소",
            "hope": "시계열 분석 지도, 모델 하이퍼파라미터 튜닝 지원",
            "ai_category": "ML",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 4},
                {"category": "AI/ML", "skill": "scikit-learn", "level": 3},
                {"category": "AI/ML", "skill": "XGBoost", "level": 2}
            ]
        },
        {
            "subject": "제조 불량품 자동 검출 시스템",
            "current_work": "제조 라인에서 불량품 검사는 육안 검사로 진행되며 검사자의 피로도에 따라 정확도가 달라집니다.",
            "pain_point": "불량품 검출률 75%, 검사 시간 제품당 10초 소요, 인력 의존적",
            "improvement_idea": "딥러닝 이미지 분류 모델(CNN)로 실시간 불량품 자동 검출 시스템 구축",
            "expected_effect": "검출률 95% 이상, 검사 시간 1초로 단축, 인력 50% 절감",
            "hope": "학습 데이터 라벨링 지원, 모델 경량화 및 엣지 배포 지원",
            "ai_category": "DL",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 3},
                {"category": "AI/ML", "skill": "TensorFlow", "level": 3},
                {"category": "AI/ML", "skill": "Computer Vision", "level": 2}
            ]
        },
        {
            "subject": "영업 프로세스 자동화 AI Agent",
            "current_work": "영업 팀의 일일 업무는 리드 발굴, 이메일 발송, 미팅 일정 조율 등 반복 작업이 많습니다.",
            "pain_point": "영업사원 시간의 60%가 행정 업무에 소요, 실제 영업 활동 시간 부족",
            "improvement_idea": "AI Agent로 리드 발굴, 이메일 자동 작성/발송, 일정 조율, CRM 업데이트 자동화",
            "expected_effect": "행정 업무 시간 70% 절감, 영업 활동 시간 2배 증가, 매출 30% 증대",
            "hope": "멀티 스텝 워크플로우 설계 지원, API 연동 지원",
            "ai_category": "AI Agent",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 3},
                {"category": "AI/ML", "skill": "LangChain", "level": 2},
                {"category": "자동화", "skill": "RPA", "level": 2}
            ]
        },
        {
            "subject": "마케팅 캠페인 효과 분석 대시보드",
            "current_work": "마케팅 데이터가 여러 플랫폼에 분산되어 있어 통합 분석이 어렵습니다.",
            "pain_point": "데이터 수집에 2일 소요, 수동 분석으로 인사이트 도출 지연, 의사결정 속도 저하",
            "improvement_idea": "AI 기반 데이터 통합 및 자동 분석 대시보드 구축, 예측 인사이트 제공",
            "expected_effect": "분석 시간 90% 단축, 실시간 인사이트 제공, ROI 20% 향상",
            "hope": "BI 도구 연동 지원, 예측 분석 모델 개발 지원",
            "ai_category": "데이터분석",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 4},
                {"category": "데이터 분석", "skill": "Pandas", "level": 4},
                {"category": "시각화", "skill": "Tableau", "level": 3}
            ]
        },
        {
            "subject": "코드 리뷰 자동화 AI 어시스턴트",
            "current_work": "코드 리뷰는 시니어 개발자가 수동으로 진행하며 시간이 많이 소요됩니다.",
            "pain_point": "리뷰 대기 시간 평균 2일, 시니어 개발자 업무 부담, 리뷰 품질 편차",
            "improvement_idea": "LLM 기반 코드 리뷰 AI로 버그, 보안 취약점, 코딩 컨벤션 자동 검토",
            "expected_effect": "리뷰 시간 50% 단축, 코드 품질 향상, 시니어 개발자 부담 감소",
            "hope": "코드 분석 모델 파인튜닝 지원, Git 연동 지원",
            "ai_category": "LLM",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 4},
                {"category": "프로그래밍", "skill": "Java", "level": 3},
                {"category": "AI/ML", "skill": "GPT", "level": 2}
            ]
        },
        {
            "subject": "고객 이탈 예측 모델",
            "current_work": "고객 이탈은 사후에 파악되어 선제적 대응이 불가능합니다.",
            "pain_point": "월평균 5% 고객 이탈, 이탈 원인 파악 어려움, 리텐션 비용 증가",
            "improvement_idea": "ML 모델로 고객 행동 데이터 기반 이탈 위험도 예측 및 맞춤형 리텐션 전략 수립",
            "expected_effect": "이탈률 30% 감소, 리텐션 비용 40% 절감, 고객 생애 가치 증대",
            "hope": "Feature engineering 지원, 모델 해석 가능성 확보 지원",
            "ai_category": "ML",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 4},
                {"category": "AI/ML", "skill": "scikit-learn", "level": 3},
                {"category": "데이터 분석", "skill": "SQL", "level": 4}
            ]
        },
        {
            "subject": "회의록 자동 생성 시스템",
            "current_work": "회의 후 회의록 작성에 평균 1시간이 소요되며 작성 품질이 일정하지 않습니다.",
            "pain_point": "회의록 작성 시간 부담, 주요 내용 누락, 공유 지연",
            "improvement_idea": "음성인식 + LLM으로 회의 내용 자동 전사 및 요약, 액션 아이템 추출",
            "expected_effect": "회의록 작성 시간 90% 절감, 내용 정확도 향상, 즉시 공유 가능",
            "hope": "음성인식 모델 커스터마이징, 요약 품질 향상 지원",
            "ai_category": "LLM",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 3},
                {"category": "AI/ML", "skill": "Speech Recognition", "level": 2}
            ]
        },
        {
            "subject": "재고 최적화 추천 시스템",
            "current_work": "창고 재고 관리는 경험에 의존하여 과잉 재고 또는 품절이 자주 발생합니다.",
            "pain_point": "재고 회전율 저하, 창고 공간 낭비, 기회 손실 발생",
            "improvement_idea": "ML 추천 시스템으로 최적 재고 수준 예측 및 발주 시점 자동 알림",
            "expected_effect": "재고 비용 25% 절감, 품절률 60% 감소, 창고 효율성 향상",
            "hope": "재고 데이터 분석 지원, 실시간 예측 시스템 구축 지원",
            "ai_category": "ML",
            "tech_capabilities": [
                {"category": "프로그래밍", "skill": "Python", "level": 3},
                {"category": "데이터 분석", "skill": "Pandas", "level": 4}
            ]
        }
    ]
    
    # Create applications
    applications = []
    grades = ["S", "A", "B", "C", "D"]
    grade_weights = [0.1, 0.3, 0.4, 0.15, 0.05]  # S가 적고 B가 많도록
    
    batch_id = "2026-1Q"
    
    for i, template in enumerate(templates, 1):
        dept = random.choice(departments)
        
        # Pre-survey (random answers)
        pre_survey = {
            "q1": random.choice(["예", "아니오"]),
            "q2": random.choice(["예", "아니오"]),
            "q3": random.choice(["예", "아니오"]),
            "q4": random.choice(["예", "아니오"]),
            "q5": random.choice(["예", "아니오"]),
            "q6": random.choice(["예", "아니오"])
        }
        
        # AI grade
        ai_grade = random.choices(grades, weights=grade_weights)[0]
        
        # AI evaluation detail
        criteria_names = [
            "경영성과", "전략과제 유사도", "확장가능성", "참여자 역량",
            "실현가능성", "Pain Point 명확성", "데이터 준비도", "ROI 측정 가능성"
        ]
        
        grade_to_score = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
        base_score = grade_to_score[ai_grade]
        
        evaluation_detail = {}
        for criteria in criteria_names:
            score = max(1, min(5, base_score + random.randint(-1, 1)))
            criteria_grade = [g for g, s in grade_to_score.items() if s == score][0]
            evaluation_detail[criteria] = {
                "grade": criteria_grade,
                "score": score,
                "comment": f"{criteria}에 대한 평가 코멘트입니다."
            }
        
        # AI summary
        ai_summary = f"""- {template['subject']} 프로젝트
- 주요 Pain Point: {template['pain_point'][:50]}...
- 기대 효과: {template['expected_effect'][:50]}...
- AI 기술: {template['ai_category']}
- 종합 평가: {ai_grade}등급"""
        
        # AI categories
        ai_categories = [
            {"category": template["ai_category"], "priority": 1, "confidence": 0.9}
        ]
        
        # User evaluation (50% of applications)
        user_grade = None
        user_comment = None
        user_evaluated_by = None
        user_evaluated_at = None
        status = "ai_evaluated"
        
        if random.random() < 0.5:
            # Find reviewer for this department
            reviewer = next((r for r in reviewers if r.department_id == dept.id), None)
            if reviewer:
                user_grade = random.choices(grades, weights=grade_weights)[0]
                user_comment = f"심사위원 평가 의견: 본 과제는 {user_grade}등급으로 평가되었습니다."
                user_evaluated_by = reviewer.id
                user_evaluated_at = datetime.utcnow() - timedelta(days=random.randint(1, 10))
                status = "user_evaluated"
        
        app = Application(
            confluence_page_id=f"DUMMY{i:03d}",
            confluence_page_url=f"https://confluence.company.com/pages/viewpage.action?pageId=DUMMY{i:03d}",
            subject=template["subject"],
            division=dept.name,
            department_id=dept.id,
            participant_count=random.randint(2, 8),
            representative_name=f"김{chr(0xAC00 + random.randint(0, 100))}동",
            representative_knox_id=f"user{i:03d}",
            pre_survey=pre_survey,
            current_work=template["current_work"],
            pain_point=template["pain_point"],
            improvement_idea=template["improvement_idea"],
            expected_effect=template["expected_effect"],
            hope=template["hope"],
            tech_capabilities=template["tech_capabilities"],
            ai_category_primary=template["ai_category"],
            ai_categories=ai_categories,
            ai_grade=ai_grade,
            ai_summary=ai_summary,
            ai_evaluation_detail=evaluation_detail,
            ai_evaluated_at=datetime.utcnow() - timedelta(days=random.randint(5, 15)),
            user_grade=user_grade,
            user_comment=user_comment,
            user_evaluated_by=user_evaluated_by,
            user_evaluated_at=user_evaluated_at,
            batch_id=batch_id,
            status=status,
            created_at=datetime.utcnow() - timedelta(days=random.randint(15, 30))
        )
        
        db.add(app)
        db.flush()
        applications.append(app)
        
        # Add AI evaluation history
        ai_history = EvaluationHistory(
            application_id=app.id,
            evaluator_id=None,
            evaluator_type="AI",
            grade=ai_grade,
            summary=ai_summary,
            evaluation_detail=evaluation_detail,
            ai_categories=ai_categories,
            created_at=app.ai_evaluated_at
        )
        db.add(ai_history)
        
        # Add user evaluation history if exists
        if user_evaluated_by:
            user_history = EvaluationHistory(
                application_id=app.id,
                evaluator_id=user_evaluated_by,
                evaluator_type="USER",
                grade=user_grade,
                summary=user_comment,
                evaluation_detail=None,
                ai_categories=ai_categories,
                created_at=user_evaluated_at
            )
            db.add(user_history)
    
    db.commit()
    print(f"✅ Created {len(applications)} applications with evaluation histories")
    print(f"📊 Grade distribution:")
    for grade in grades:
        count = sum(1 for app in applications if app.ai_grade == grade)
        print(f"   {grade}: {count} ({count/len(applications)*100:.1f}%)")
    
    print(f"👥 User evaluations: {sum(1 for app in applications if app.user_grade is not None)}/{len(applications)}")
    print("✅ Dummy data generation completed!")


if __name__ == "__main__":
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        generate_dummy_data(db)
    finally:
        db.close()
