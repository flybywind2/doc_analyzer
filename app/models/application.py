"""
Application model
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Application(Base):
    """Application model"""
    __tablename__ = "applications"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    confluence_page_id = Column(String(50), unique=True, nullable=False, index=True)
    confluence_page_url = Column(String(500))
    
    # 기본사항
    subject = Column(String(500))  # 과제명
    division = Column(String(100))  # 사업부 원본 텍스트
    department_id = Column(Integer, ForeignKey("departments.id"), index=True)
    participant_count = Column(Integer)  # 참여 인원 수
    representative_name = Column(String(100))  # 과제 대표자
    representative_knox_id = Column(String(50))
    
    # 사전 설문 (JSON)
    pre_survey = Column(JSON)  # {"q1": "예", "q2": "아니오", ...}
    
    # 신청 내용
    current_work = Column(Text)  # 현재 업무
    pain_point = Column(Text)  # Pain point
    improvement_idea = Column(Text)  # 개선 아이디어
    expected_effect = Column(Text)  # 기대 효과
    hope = Column(Text)  # 바라는 점
    
    # 기술 역량 (JSON)
    tech_capabilities = Column(JSON)  # [{"category": "프로그래밍", "skill": "Python", "level": 2}]
    
    # 기타 파싱 데이터
    etc_data = Column(JSON)
    
    # AI 분류 결과
    ai_category_primary = Column(String(50), index=True)  # 1순위
    ai_categories = Column(JSON)  # [{"category": "RAG", "priority": 1}, ...]
    
    # AI 평가 결과
    ai_grade = Column(String(10), index=True)  # S/A/B/C/D
    ai_summary = Column(Text)  # Bullet 형태 요약
    ai_evaluation_detail = Column(JSON)  # 항목별 상세
    ai_evaluated_at = Column(DateTime(timezone=True))
    
    # 사용자 평가 결과
    user_grade = Column(String(10), index=True)
    user_comment = Column(Text)
    user_evaluated_by = Column(Integer, ForeignKey("users.id"))
    user_evaluated_at = Column(DateTime(timezone=True))
    
    # 메타
    batch_id = Column(String(50), index=True)  # 회차 (예: "2026-1Q")
    status = Column(String(20), default="pending")  # pending, ai_evaluated, user_evaluated
    parse_error_log = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    department = relationship("Department", back_populates="applications")
    evaluator = relationship("User", foreign_keys=[user_evaluated_by])
    evaluation_histories = relationship("EvaluationHistory", back_populates="application")
