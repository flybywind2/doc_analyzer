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
        app_info = f"""
# AI 과제 지원서 평가

## 과제 기본 정보
- 과제명: {application.subject or 'N/A'}
- 사업부: {application.division or 'N/A'}
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

## 평가 기준 ({len(criteria_list)}개 항목)
"""
        
        for i, criteria in enumerate(criteria_list, 1):
            app_info += f"""
{i}. **{criteria.name}** (가중치: {criteria.weight})
   - {criteria.description}
   - 평가 가이드: {criteria.evaluation_guide}
"""
        
        prompt = f"""{app_info}

---

## 평가 지침
1. 각 평가 기준에 대해 **지원서에 명시된 내용을 우선**으로 평가하세요.
2. 명시되지 않았지만 추론 가능한 경우, **"[AI 추론]"** 표시를 명확히 하세요.
3. 각 항목을 S/A/B/C/D 5단계로 평가하세요:
   - S: 매우 우수 (5점)
   - A: 우수 (4점)
   - B: 보통 (3점)
   - C: 미흡 (2점)
   - D: 매우 미흡 (1점)

4. 가중치를 반영하여 종합 등급을 산출하세요.
5. 과제 요약은 **3-5개 bullet point** 형태로 작성하세요.

## 응답 형식 (JSON)
다음 JSON 형식으로 정확히 응답하세요:

{{
  "evaluation_detail": {{
    "경영성과": {{"grade": "A", "score": 4, "comment": "구체적인 평가 내용..."}},
    "전략과제 유사도": {{"grade": "B", "score": 3, "comment": "구체적인 평가 내용..."}},
    ...
  }},
  "overall_grade": "A",
  "overall_score": 4.2,
  "summary": "- Bullet point 1\\n- Bullet point 2\\n- Bullet point 3"
}}

**중요: 반드시 유효한 JSON 형식으로 응답하세요.**
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
            # Get evaluation criteria if not provided
            if criteria_list is None:
                criteria_list = db.query(EvaluationCriteria).filter(
                    EvaluationCriteria.is_active == True
                ).order_by(EvaluationCriteria.display_order).all()
            
            if not criteria_list:
                print("❌ No evaluation criteria found")
                return False
            
            # Build prompt
            prompt = self.build_evaluation_prompt(application, criteria_list)
            
            # Evaluate with LLM
            print(f"🤖 Evaluating application {application.id} ({application.subject})...")
            result = self.evaluate_with_llm(prompt)
            
            # Extract results
            evaluation_detail = result.get("evaluation_detail", {})
            overall_grade = result.get("overall_grade") or self.calculate_overall_grade(evaluation_detail)
            summary = result.get("summary", "")
            
            # Update application
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
                ai_categories=application.ai_categories
            )
            db.add(history)
            
            db.commit()
            print(f"✅ Application {application.id} evaluated: {overall_grade}")
            return True
            
        except Exception as e:
            print(f"❌ Error evaluating application {application.id}: {e}")
            db.rollback()
            return False


# Singleton instance
llm_evaluator = LLMEvaluator()
