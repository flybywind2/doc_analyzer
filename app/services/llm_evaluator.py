"""
LLM Evaluator Service
"""
import uuid
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings
from app.models.application import Application
from app.models.evaluation import EvaluationCriteria, EvaluationHistory
from app.services.rate_limiter import RateLimiter


class LLMEvaluator:
    """LLM-based application evaluator"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.llm_api_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model_name,
            temperature=0.1,  # 일관성 확보
            default_headers={
                "x-dep-ticket": settings.llm_credential_key,
                "Send-System-Name": settings.llm_system_name,
                "User-ID": settings.llm_user_id,
                "User-Type": "AD",
                "Prompt-Msg-Id": str(uuid.uuid4()),
                "Completion-Msg-Id": str(uuid.uuid4()),
            },
        )
        # Rate limiter: 20 calls per minute
        self.rate_limiter = RateLimiter(max_calls=20, time_window=60)
    
    def build_evaluation_prompt(
        self, 
        application: Application, 
        criteria_list: List[EvaluationCriteria]
    ) -> str:
        """
        Build evaluation prompt for LLM
        
        Args:
            application: Application to evaluate
            criteria_list: List of evaluation criteria
            
        Returns:
            Formatted prompt string
        """
        # 과제 정보 구성
        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"
        
        system_prompt = f"""당신은 글로벌 반도체 대기업의 AI 전문가입니다.
조직: {department_info}

역할: 지원서 내용을 객관적으로 요약하고 분석합니다.

중요 원칙:
1. 지원서에 작성된 내용만을 기반으로 요약 (할루시네이션 금지)
2. {department_info} 조직의 업무 특성을 고려한 해석
3. 사실 기반의 객관적 분석
4. 과장하거나 추측하지 말 것
"""

        app_info = f"""
# AI 과제 지원서 평가

## 과제 기본 정보
- 과제명: {application.subject or 'N/A'}
- 조직: {department_info}
- 참여 인원: {application.participant_count or 'N/A'}명
- 대표자: {application.representative_name or 'N/A'}

## 신청 내용
### 현재 업무
{application.current_work or 'N/A'}

### Pain Point (해결하고자 하는 문제)
{application.pain_point or 'N/A'}

### 개선 아이디어
{application.improvement_idea or 'N/A'}

### 기대 효과
{application.expected_effect or 'N/A'}

### 바라는 점
{application.hope or 'N/A'}

## 사전 설문
{json.dumps(application.pre_survey, ensure_ascii=False, indent=2) if application.pre_survey else 'N/A'}

## 참여자 기술 역량
{json.dumps(application.tech_capabilities, ensure_ascii=False, indent=2) if application.tech_capabilities else 'N/A'}

---

## 요약 요청사항

지원서 내용을 바탕으로 다음 4가지만 간결하게 요약하세요:

### 1. AI 기술 분류
지원서에서 언급된 AI 기술을 다음 중 **하나만** 선택하세요:
- **예측**: 미래 값 예측, 수요 예측, 트렌드 분석
- **분류**: 이미지/텍스트 분류, 불량 검출, 카테고리 분류
- **챗봇**: 대화형 인터페이스, 자동 응답, Q&A
- **에이전트**: 자율 의사결정, 복잡한 작업 자동화, 워크플로우 자동화
- **최적화**: 자원 최적화, 스케줄링, 경로 최적화
- **강화학습**: 학습 기반 의사결정, 시뮬레이션 최적화

### 2. 조직 관점의 경영효과
{department_info} 조직 관점에서 이 과제의 경영효과를 요약하세요 (2-3문장):
- 지원서에 작성된 기대효과 기반으로만 작성
- 추측이나 과장 금지

### 3. AI 관점의 구현 가능성
지원서 내용(참여인원, 기술역량, 데이터 등)을 바탕으로 구현 가능성 평가 (2-3문장):
- 지원서에 작성된 내용만 참고
- 기술적 난이도, 데이터 확보, 팀 역량 등을 객관적으로 평가

### 4. 전체 지원서 5줄 요약
이 지원서의 핵심 내용을 5줄로 요약:
1. 과제 목적 (1줄)
2. 현재 문제 (1줄)
3. 해결 방안 (1줄)
4. 기대 효과 (1줄)
5. 구현 계획 (1줄)
"""
        
        prompt = f"""{system_prompt}

{app_info}

---

## 응답 형식 (JSON)
다음 JSON 형식으로 정확히 응답하세요:

{{
  "ai_category": "예측" 또는 "분류" 또는 "챗봇" 또는 "에이전트" 또는 "최적화" 또는 "강화학습",
  "business_impact": "조직 관점의 경영효과를 2-3문장으로 요약 (지원서 내용 기반)",
  "technical_feasibility": "AI 관점의 구현 가능성을 2-3문장으로 평가 (지원서 내용 기반)",
  "five_line_summary": [
    "1. 과제 목적",
    "2. 현재 문제",
    "3. 해결 방안",
    "4. 기대 효과",
    "5. 구현 계획"
  ]
}}

**중요 규칙:**
1. 유효한 JSON 형식 필수
2. ai_category는 6개 선택지 중 하나만 (예측/분류/챗봇/에이전트/최적화/강화학습)
3. 지원서에 작성된 내용만 사용 (할루시네이션 금지)
4. 추측이나 과장 금지 - 사실만 기반
5. {department_info} 조직 특성 반영
6. 간결하고 명확하게 (요약의 목적)
"""
        return prompt
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(Exception)
    )
    def evaluate_with_llm(self, prompt: str) -> Dict[str, Any]:
        """
        Evaluate application using LLM with retry logic
        
        Args:
            prompt: Evaluation prompt
            
        Returns:
            Evaluation result dictionary
            
        Raises:
            Exception: If evaluation fails after retries
        """
        # Apply rate limiting before LLM call
        self.rate_limiter.wait_if_needed()
        
        response = self.llm.invoke(prompt)
        content = response.content
        
        # JSON 파싱 시도
        try:
            # Markdown code block 제거
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            return result
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            print(f"Response content: {content}")
            raise
    
    def calculate_overall_grade(self, evaluation_detail: Dict[str, Any]) -> str:
        """
        Calculate overall grade from evaluation details
        
        Args:
            evaluation_detail: Dictionary of evaluation scores
            
        Returns:
            Overall grade (S/A/B/C/D)
        """
        total_score = 0
        count = 0
        
        for item in evaluation_detail.values():
            if isinstance(item, dict) and "score" in item:
                total_score += item["score"]
                count += 1
        
        if count == 0:
            return "C"
        
        avg_score = total_score / count
        
        if avg_score >= 4.5:
            return "S"
        elif avg_score >= 3.5:
            return "A"
        elif avg_score >= 2.5:
            return "B"
        elif avg_score >= 1.5:
            return "C"
        else:
            return "D"
    
    def evaluate_application(
        self, 
        db: Session, 
        application: Application,
        criteria_list: Optional[List[EvaluationCriteria]] = None
    ) -> bool:
        """
        Evaluate single application
        
        Args:
            db: Database session
            application: Application to evaluate
            criteria_list: Evaluation criteria (optional, will fetch if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get evaluation criteria if not provided (backward compatibility)
            if criteria_list is None:
                criteria_list = db.query(EvaluationCriteria).filter(
                    EvaluationCriteria.is_active == True
                ).order_by(EvaluationCriteria.display_order).all()
            
            # Build prompt
            prompt = self.build_evaluation_prompt(application, criteria_list or [])
            
            # Evaluate with LLM
            print(f"🤖 Evaluating application {application.id} ({application.subject})...")
            result = self.evaluate_with_llm(prompt)
            
            # Extract simplified format results
            ai_category = result.get("ai_category", "분류")
            business_impact = result.get("business_impact", "")
            technical_feasibility = result.get("technical_feasibility", "")
            five_line_summary = result.get("five_line_summary", [])
            
            # Build AI categories for compatibility
            ai_categories = [{
                "category": ai_category,
                "description": "지원서 기반 AI 요약"
            }]
            
            # Build evaluation detail - simplified 4-item format
            evaluation_detail = {
                "ai_category": ai_category,
                "business_impact": business_impact,
                "technical_feasibility": technical_feasibility,
                "five_line_summary": five_line_summary
            }
            
            # Simple grade based on feasibility tone
            if "어렵" in technical_feasibility or "불가능" in technical_feasibility:
                overall_grade = "C"
            elif "가능" in technical_feasibility and "충분" in technical_feasibility:
                overall_grade = "A"
            else:
                overall_grade = "B"
            
            # Build summary
            summary_parts = []
            summary_parts.append(f"**AI 기술 분류**: {ai_category}\n\n")
            summary_parts.append(f"**조직 관점의 경영효과**\n{business_impact}\n\n")
            summary_parts.append(f"**AI 관점의 구현 가능성**\n{technical_feasibility}\n\n")
            summary_parts.append(f"**전체 지원서 5줄 요약**\n" + "\n".join(five_line_summary))
            
            summary = "".join(summary_parts)
            
            # Update application
            application.ai_categories = ai_categories
            application.ai_category_primary = ai_category
            application.ai_evaluation_detail = evaluation_detail
            application.ai_grade = overall_grade
            application.ai_summary = summary
            application.ai_evaluated_at = datetime.utcnow()
            application.status = "ai_evaluated"
            
            # Save evaluation history
            history = EvaluationHistory(
                application_id=application.id,
                evaluator_id=None,
                evaluator_type="AI",
                grade=overall_grade,
                summary=summary,
                evaluation_detail=evaluation_detail,
                ai_categories=ai_categories
            )
            db.add(history)
            
            db.commit()
            print(f"✅ Application {application.id} evaluated: {overall_grade} ({ai_category})")
            return True
            
        except Exception as e:
            print(f"❌ Error evaluating application {application.id}: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return False
    
    def _score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade"""
        if score >= 4.5:
            return "S"
        elif score >= 3.5:
            return "A"
        elif score >= 2.5:
            return "B"
        elif score >= 1.5:
            return "C"
        else:
            return "D"


# Singleton instance
llm_evaluator = LLMEvaluator()
