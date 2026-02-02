"""
Evaluation models
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class EvaluationCriteria(Base):
    """Evaluation Criteria model"""
    __tablename__ = "evaluation_criteria"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id = Column(String(50), index=True)  # NULL이면 기본 기준
    name = Column(String(100), nullable=False)
    description = Column(Text)
    weight = Column(Float, default=1.0)
    evaluation_guide = Column(Text)  # LLM 프롬프트용
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class EvaluationHistory(Base):
    """Evaluation History model"""
    __tablename__ = "evaluation_history"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
    evaluator_id = Column(Integer, ForeignKey("users.id"))  # NULL이면 AI
    evaluator_type = Column(String(10), nullable=False)  # 'AI' or 'USER'
    grade = Column(String(10))
    summary = Column(Text)
    evaluation_detail = Column(JSON)
    ai_categories = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    application = relationship("Application", back_populates="evaluation_histories")
    evaluator = relationship("User", back_populates="evaluations", foreign_keys=[evaluator_id])
