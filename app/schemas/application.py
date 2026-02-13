"""
Application schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ApplicationBase(BaseModel):
    """Base application schema"""
    subject: Optional[str] = None
    division: Optional[str] = None
    department_id: Optional[int] = None
    participant_count: Optional[int] = None
    representative_name: Optional[str] = None
    representative_knox_id: Optional[str] = None


class ApplicationCreate(ApplicationBase):
    """Schema for creating application"""
    confluence_page_id: str
    confluence_page_url: Optional[str] = None
    batch_id: Optional[str] = None


class ApplicationUpdate(BaseModel):
    """Schema for updating application"""
    subject: Optional[str] = None
    division: Optional[str] = None
    department_id: Optional[int] = None
    participant_count: Optional[int] = None
    representative_name: Optional[str] = None
    representative_knox_id: Optional[str] = None
    current_work: Optional[str] = None
    pain_point: Optional[str] = None
    improvement_idea: Optional[str] = None
    expected_effect: Optional[str] = None
    hope: Optional[str] = None


class ApplicationResponse(ApplicationBase):
    """Schema for application response"""
    id: int
    confluence_page_id: str
    confluence_page_url: Optional[str]
    
    # 신청 내용
    current_work: Optional[str]
    pain_point: Optional[str]
    improvement_idea: Optional[str]
    expected_effect: Optional[str]
    hope: Optional[str]
    
    # JSON 필드
    pre_survey: Optional[Dict[str, Any]]
    tech_capabilities: Optional[List[Dict[str, Any]]]
    etc_data: Optional[Dict[str, Any]]
    
    # AI 분류 및 평가
    ai_category_primary: Optional[str]
    ai_categories: Optional[List[Dict[str, Any]]]
    ai_grade: Optional[str]
    ai_summary: Optional[str]
    ai_evaluation_detail: Optional[Dict[str, Any]]
    ai_evaluated_at: Optional[datetime]
    
    # 사용자 평가
    user_grade: Optional[str]
    user_comment: Optional[str]
    user_evaluated_by: Optional[int]
    user_evaluated_at: Optional[datetime]
    
    # 메타
    batch_id: Optional[str]
    status: str
    parse_error_log: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    # 관계
    department_name: Optional[str] = None
    evaluator_name: Optional[str] = None
    user_has_evaluated: bool = False  # 현재 사용자가 이 지원서를 평가했는지 여부

    class Config:
        from_attributes = True


class ApplicationFilter(BaseModel):
    """Schema for filtering applications"""
    department_id: Optional[int] = None
    batch_id: Optional[str] = None
    ai_grade: Optional[str] = None
    user_grade: Optional[str] = None
    ai_category: Optional[str] = None
    status: Optional[str] = None
    search: Optional[str] = None  # 과제명, 대표자명 검색
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class UserEvaluationSubmit(BaseModel):
    """Schema for user evaluation submission"""
    grade: str = Field(..., pattern="^(S|A|B|C|D)$")
    comment: Optional[str] = None


class ConfluenceSyncRequest(BaseModel):
    """Schema for Confluence sync request"""
    batch_id: Optional[str] = None
    force_update: bool = False  # 기존 데이터도 업데이트할지 여부


class ConfluenceSingleSyncRequest(BaseModel):
    """Schema for single page Confluence sync request"""
    page_id: str = Field(..., description="Confluence page ID to sync")
    batch_id: Optional[str] = None
    force_update: bool = True  # 개별 동기화는 기본적으로 업데이트 허용
