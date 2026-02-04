"""
Evaluation schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class EvaluationCriteriaBase(BaseModel):
    """Base evaluation criteria schema"""
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    weight: float = Field(default=1.0, ge=0.0)
    evaluation_guide: Optional[str] = None
    display_order: int = Field(default=0, ge=0)
    is_active: bool = True


class EvaluationCriteriaCreate(EvaluationCriteriaBase):
    """Schema for creating evaluation criteria"""
    batch_id: Optional[str] = None


class EvaluationCriteriaUpdate(BaseModel):
    """Schema for updating evaluation criteria"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    weight: Optional[float] = Field(None, ge=0.0)
    evaluation_guide: Optional[str] = None
    display_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class EvaluationCriteriaResponse(EvaluationCriteriaBase):
    """Schema for evaluation criteria response"""
    id: int
    batch_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class EvaluationHistoryResponse(BaseModel):
    """Schema for evaluation history response"""
    id: int
    application_id: int
    evaluator_id: Optional[int]
    evaluator_type: str
    grade: Optional[str]
    summary: Optional[str]
    evaluation_detail: Optional[Dict[str, Any]]
    ai_categories: Optional[List[Dict[str, Any]]]
    created_at: datetime
    
    # 관계
    evaluator_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class AIEvaluationRequest(BaseModel):
    """Schema for AI evaluation request"""
    application_ids: Optional[List[int]] = None  # None이면 전체 미평가 지원서
    force_re_evaluate: bool = False  # True면 이미 평가된 것도 재평가


class AIEvaluationResponse(BaseModel):
    """Schema for AI evaluation response"""
    success_count: int
    fail_count: int
    failed_ids: List[int]
    error_messages: List[str]


class DepartmentBase(BaseModel):
    """Base department schema"""
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    total_employees: int = Field(default=0, ge=0)


class DepartmentCreate(DepartmentBase):
    """Schema for creating department"""
    pass


class DepartmentUpdate(BaseModel):
    """Schema for updating department"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    total_employees: Optional[int] = Field(None, ge=0)


class DepartmentResponse(DepartmentBase):
    """Schema for department response"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class AICategoryBase(BaseModel):
    """Base AI category schema"""
    name: str = Field(..., max_length=50)
    description: Optional[str] = None
    keywords: Optional[List[str]] = None  # List of keywords
    display_order: int = Field(default=0, ge=0)
    is_active: bool = True


class AICategoryCreate(AICategoryBase):
    """Schema for creating AI category"""
    pass


class AICategoryUpdate(BaseModel):
    """Schema for updating AI category"""
    name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    display_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class AICategoryResponse(AICategoryBase):
    """Schema for AI category response"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True
