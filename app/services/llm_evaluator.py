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
        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"
        
        system_prompt = f"""당신은 글로벌 반도체 대기업의 AI 과제 심사 담당자입니다.
조직: {department_info}

당신의 역할:
- 해당 조직의 관점에서 AI 과제의 사업적 가치(Biz Impact)와 실현 가능성(Feasibility)을 평가
- 심사위원들이 긍정적으로 평가할 수 있도록 과제의 강점을 부각
- 조직의 업무 특성과 전략적 방향성을 고려한 평가

평가 원칙:
1. 사업부와 부서의 특성을 반영한 맞춤형 평가
2. 실질적인 업무 개선 효과에 초점
3. 기술적 실현 가능성을 현실적으로 평가
4. 심사위원의 평가를 지원하는 관점에서 작성
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

## 평가 요청사항

다음 4가지 관점에서 평가해주세요:

### 1. AI 기술 분류
과제에서 활용하려는 AI 기술을 다음 중 하나로 분류하고, 선택 이유를 설명하세요:
- **ML (Machine Learning)**: 데이터 기반 예측, 분류, 회귀 분석 등
- **챗봇 (Chatbot)**: 대화형 인터페이스, 자동 응답, Q&A 시스템 등
- **Agent**: 자율적 의사결정, 복잡한 작업 자동화, 멀티스텝 프로세스 등

### 2. 왜 이 과제를 추천하는가?
{department_info} 조직 관점에서 이 과제가 가치 있는 이유를 설명하세요:
- 어떤 업무 문제를 해결하나요?
- 조직에 어떤 긍정적 영향을 주나요?
- 왜 지금 이 과제가 필요한가요?
- 이 과제의 핵심 가치는 무엇인가요?

### 3. 실현 가능성은 어떤가요?
실제로 구현할 수 있을지 현실적으로 평가하세요:
- 기술적으로 가능한 과제인가요? (난이도: 상/중/하)
- 필요한 데이터를 확보할 수 있나요?
- 팀의 역량이 충분한가요?
- 어떤 어려움이 예상되나요?
- 언제쯤 완성할 수 있을까요?

### 4. 한줄 요약
이 과제를 한 문장으로 요약하고 추천도를 제시하세요.
"""
        
        prompt = f"""{system_prompt}

{app_info}

---

## 응답 형식 (JSON)
다음 JSON 형식으로 정확히 응답하세요:

{{
  "ai_technology_category": {{
    "category": "ML" 또는 "챗봇" 또는 "Agent",
    "reason": "이 기술로 분류한 이유를 2-3문장으로 설명"
  }},
  "why_recommend": {{
    "problem_solving": "어떤 업무 문제를 해결하나요? (2-3문장)",
    "positive_impact": "조직에 어떤 긍정적 영향을 주나요? (2-3문장)",
    "urgency": "왜 지금 이 과제가 필요한가요? (1-2문장)",
    "core_value": "이 과제의 핵심 가치는 무엇인가요? (2-3문장)"
  }},
  "feasibility_assessment": {{
    "is_feasible": true,  // true or false
    "technical_difficulty": "상" 또는 "중" 또는 "하",
    "difficulty_reason": "난이도 판단 이유 (2-3문장)",
    "data_availability": "필요한 데이터를 확보할 수 있나요? (2-3문장)",
    "team_capability": "팀의 역량이 충분한가요? (2-3문장)",
    "expected_challenges": [
      "예상 어려움 1",
      "예상 어려움 2"
    ],
    "timeline_estimate": "언제쯤 완성할 수 있을까요? (예: 3-6개월)"
  }},
  "one_line_summary": {{
    "summary": "이 과제를 한 문장으로 요약 (1문장, 핵심만)",
    "recommendation": "강력 추천" 또는 "추천" 또는 "조건부 추천" 또는 "보류",
    "recommendation_reason": "추천도를 선택한 이유 (1-2문장)"
  }}
}}

**중요사항:**
1. 반드시 유효한 JSON 형식으로 응답하세요
2. 모든 필드를 빠짐없이 채워주세요
3. 점수(score)는 절대 포함하지 마세요 - 심사위원이 숫자에 영향받지 않도록
4. {department_info} 조직의 특성을 반영하여 평가하세요
5. 간결하고 명확하게 작성하세요 - 심사위원이 빠르게 이해할 수 있도록
6. 긍정적이고 건설적인 관점으로 작성하세요
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
            
            # Extract new format results
            ai_tech = result.get("ai_technology_category", {})
            why_recommend = result.get("why_recommend", {})
            feasibility = result.get("feasibility_assessment", {})
            one_liner = result.get("one_line_summary", {})
            
            # Build AI categories for compatibility
            ai_categories = [{
                "category": ai_tech.get("category", "Unknown"),
                "reason": ai_tech.get("reason", "")
            }]
            
            # Build evaluation detail for new format (NO SCORES)
            evaluation_detail = {
                "ai_technology": ai_tech,
                "why_recommend": why_recommend,
                "feasibility_assessment": feasibility,
                "one_line_summary": one_liner
            }
            
            # Map recommendation to grade (without showing numeric scores)
            recommendation = one_liner.get("recommendation", "추천")
            if recommendation == "강력 추천":
                overall_grade = "S"
            elif recommendation == "추천":
                overall_grade = "A"
            elif recommendation == "조건부 추천":
                overall_grade = "B"
            else:
                overall_grade = "C"
            
            # Build summary
            summary_parts = []
            summary_parts.append(f"**🤖 AI 기술**: {ai_tech.get('category', 'Unknown')}")
            summary_parts.append(f"\n\n**💡 한줄 요약**: {one_liner.get('summary', 'N/A')}")
            summary_parts.append(f"\n\n**✅ 추천도**: {recommendation}")
            if one_liner.get('recommendation_reason'):
                summary_parts.append(f"\n{one_liner.get('recommendation_reason')}")
            
            summary = "".join(summary_parts)
            
            # Update application
            application.ai_categories = ai_categories
            application.ai_category_primary = ai_tech.get("category", "Unknown")
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
            print(f"✅ Application {application.id} evaluated: {overall_grade} ({ai_tech.get('category', 'Unknown')})")
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
