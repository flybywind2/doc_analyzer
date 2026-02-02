"""
LLM Evaluator Service
"""
import re
import uuid
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings
from app.models.application import Application
from app.models.evaluation import EvaluationCriteria, EvaluationHistory
from app.services.rate_limiter import RateLimiter


class LLMEvaluator:
    """LLM-based application evaluator with ensemble support"""

    def __init__(self):
        # Primary LLM (A)
        self.llm_a = ChatOpenAI(
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

        # Secondary LLM (B) - Optional for ensemble
        self.llm_b = None
        if settings.llm_b_api_base_url and settings.llm_b_api_key:
            self.llm_b = ChatOpenAI(
                base_url=settings.llm_b_api_base_url,
                api_key=settings.llm_b_api_key,
                model=settings.llm_b_model_name or settings.llm_model_name,
                temperature=0.1,
                default_headers={
                    "x-dep-ticket": settings.llm_b_credential_key or settings.llm_credential_key,
                    "Send-System-Name": settings.llm_system_name,
                    "User-ID": settings.llm_user_id,
                    "User-Type": "AD",
                    "Prompt-Msg-Id": str(uuid.uuid4()),
                    "Completion-Msg-Id": str(uuid.uuid4()),
                },
            )
            print(f"✅ Ensemble mode enabled: LLM A ({settings.llm_model_name}) + LLM B ({settings.llm_b_model_name or settings.llm_model_name})")
        else:
            print(f"ℹ️  Single LLM mode: {settings.llm_model_name}")

        # Rate limiter: 20 calls per minute
        self.rate_limiter = RateLimiter(max_calls=20, time_window=60)

        # Criteria name to key mapping (한글 -> 영문)
        self.criteria_key_map = {
            "혁신성": "innovation",
            "실현가능성": "feasibility",
            "효과성": "impact",
            "명확성": "clarity"
        }

    def _build_criteria_guide(self, criteria_list: List[EvaluationCriteria]) -> str:
        """
        Build evaluation criteria guide from database criteria

        Args:
            criteria_list: List of evaluation criteria from DB

        Returns:
            Formatted criteria guide string
        """
        if not criteria_list:
            # Fallback to default if no criteria
            return """
**혁신성 (Innovation)**: AI 기술의 창의성과 새로움 (1-5점)
**실현가능성 (Feasibility)**: 기술적 구현 난이도와 팀 역량 (1-5점)
**효과성 (Impact)**: 조직에 미치는 경영 효과 (1-5점)
**명확성 (Clarity)**: 문제 정의와 해결 방안의 구체성 (1-5점)
""".strip()

        guide_parts = []
        for criteria in criteria_list:
            key = self.criteria_key_map.get(criteria.name, criteria.name.lower())
            guide_parts.append(f"""
**{criteria.name} ({key.capitalize()})**: {criteria.description}

{criteria.evaluation_guide}
""".strip())

        return "\n\n".join(guide_parts)

    def _build_json_format_example(self, criteria_list: List[EvaluationCriteria]) -> str:
        """
        Build JSON format example from database criteria

        Args:
            criteria_list: List of evaluation criteria from DB

        Returns:
            Formatted JSON example string
        """
        if not criteria_list:
            # Fallback to default
            criteria_list = [
                type('obj', (object,), {'name': '혁신성', 'description': 'AI 기술의 창의성과 새로움'})(),
                type('obj', (object,), {'name': '실현가능성', 'description': '기술적 구현 난이도와 팀 역량'})(),
                type('obj', (object,), {'name': '효과성', 'description': '조직에 미치는 경영 효과'})(),
                type('obj', (object,), {'name': '명확성', 'description': '문제 정의와 해결 방안의 구체성'})()
            ]

        json_parts = []
        for criteria in criteria_list:
            key = self.criteria_key_map.get(criteria.name, criteria.name.lower())
            json_parts.append(f'''    "{key}": {{
      "score": 1-5 사이의 정수,
      "rationale": "{criteria.name} 평가 근거 (2-3문장, 지원서 기반)"
    }}''')

        return ",\n".join(json_parts)

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

## 평가 요청사항

지원서 내용을 바탕으로 다음을 요약하고 평가하세요:

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

### 5. 평가 기준별 점수 및 근거 (5점 척도)
다음 기준으로 지원서를 평가하고, 각 기준마다 1-5점과 2-3문장의 근거를 제시하세요:

{self._build_criteria_guide(criteria_list)}
"""
        
        prompt = f"""{system_prompt}

{app_info}

---

## 응답 형식 (JSON)
**CRITICAL**: 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

```json
{{
  "ai_category": "예측",
  "business_impact": "조직 관점의 경영효과를 2-3문장으로 요약",
  "technical_feasibility": "AI 관점의 구현 가능성을 2-3문장으로 평가",
  "five_line_summary": [
    "1. 과제 목적",
    "2. 현재 문제",
    "3. 해결 방안",
    "4. 기대 효과",
    "5. 구현 계획"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }}
}}
```

**중요 규칙:**
1. **유효한 JSON 형식 필수** - 모든 문자열은 큰따옴표(")로 감싸기
2. **ai_category는 정확히 하나**: "예측", "분류", "챗봇", "에이전트", "최적화", "강화학습" 중 선택
3. **evaluation_scores의 각 score는 1-5 사이의 정수**
4. **모든 rationale은 지원서에 작성된 내용만 사용** (할루시네이션 금지)
5. **JSON 내부에서 줄바꿈이 필요하면 \\n 사용**
6. **마지막 항목 뒤에는 쉼표(,) 없음** - JSON 문법 준수 필수
7. **중괄호와 대괄호를 정확히 닫을 것**
8. {department_info} 조직 특성 반영

**응답은 JSON만 포함하세요. 설명이나 추가 텍스트 없이 JSON 객체만 반환하세요.**
"""
        return prompt

    def _extract_json_from_text(self, text: str) -> Optional[str]:
        """
        Extract JSON from LLM response text using multiple strategies

        Args:
            text: Raw LLM response text

        Returns:
            Extracted JSON string or None
        """
        # Strategy 1: Remove markdown code blocks
        if "```json" in text:
            parts = text.split("```json")
            if len(parts) > 1:
                json_part = parts[1].split("```")[0]
                return json_part.strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) > 1:
                json_part = parts[1]
                return json_part.strip()

        # Strategy 2: Find JSON object using regex (찾아서 { } 블록 추출)
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.finditer(json_pattern, text, re.DOTALL)
        for match in matches:
            json_candidate = match.group(0)
            try:
                # Validate it's valid JSON
                json.loads(json_candidate)
                return json_candidate
            except:
                continue

        # Strategy 3: Find first { to last }
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_candidate = text[start_idx:end_idx+1]
            return json_candidate

        # Strategy 4: Return original text (last resort)
        return text.strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(Exception)
    )
    def evaluate_with_single_llm(self, llm, prompt: str, llm_name: str = "LLM") -> Dict[str, Any]:
        """
        Evaluate application using a single LLM with robust JSON parsing

        Args:
            llm: LLM instance to use
            prompt: Evaluation prompt
            llm_name: Name of LLM for logging

        Returns:
            Evaluation result dictionary

        Raises:
            Exception: If evaluation fails after retries
        """
        # Apply rate limiting before LLM call
        self.rate_limiter.wait_if_needed()

        response = llm.invoke(prompt)
        content = response.content

        # Extract JSON from response
        json_text = self._extract_json_from_text(content)

        # Parse JSON
        try:
            result = json.loads(json_text)
            print(f"✅ {llm_name} JSON parsed successfully")
            return result
        except json.JSONDecodeError as e:
            print(f"❌ {llm_name} JSON parsing error: {e}")
            print(f"📄 Response content (first 500 chars): {content[:500]}")
            print(f"📄 Extracted JSON (first 500 chars): {json_text[:500]}")
            raise

    def evaluate_with_llm(self, prompt: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Evaluate application using LLM(s) with retry logic
        Returns results from both LLMs if ensemble mode is enabled

        Args:
            prompt: Evaluation prompt

        Returns:
            Tuple of (primary_result, secondary_result or None)

        Raises:
            Exception: If evaluation fails after retries
        """
        # Evaluate with primary LLM (A)
        result_a = self.evaluate_with_single_llm(self.llm_a, prompt, "LLM A")

        # Evaluate with secondary LLM (B) if available
        result_b = None
        if self.llm_b:
            try:
                result_b = self.evaluate_with_single_llm(self.llm_b, prompt, "LLM B")
            except Exception as e:
                print(f"⚠️  LLM B evaluation failed: {e}")
                print(f"ℹ️  Continuing with LLM A result only")

        return result_a, result_b
    
    def _ensemble_results(self, result_a: Dict[str, Any], result_b: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensemble results from two LLMs by averaging scores

        Args:
            result_a: Result from LLM A
            result_b: Result from LLM B

        Returns:
            Ensembled result dictionary
        """
        ensembled = {
            "ai_category": result_a.get("ai_category", "분류"),  # Use A's category
            "business_impact": result_a.get("business_impact", ""),  # Use A's impact
            "technical_feasibility": result_a.get("technical_feasibility", ""),  # Use A's feasibility
            "five_line_summary": result_a.get("five_line_summary", []),  # Use A's summary
            "evaluation_scores": {}
        }

        # Ensemble evaluation scores by averaging
        scores_a = result_a.get("evaluation_scores", {})
        scores_b = result_b.get("evaluation_scores", {})

        # Get all criteria keys from both results
        all_criteria = set(scores_a.keys()) | set(scores_b.keys())

        for criterion in all_criteria:
            score_a_obj = scores_a.get(criterion, {})
            score_b_obj = scores_b.get(criterion, {})

            score_a = score_a_obj.get("score", 0) if isinstance(score_a_obj, dict) else 0
            score_b = score_b_obj.get("score", 0) if isinstance(score_b_obj, dict) else 0

            rationale_a = score_a_obj.get("rationale", "") if isinstance(score_a_obj, dict) else ""
            rationale_b = score_b_obj.get("rationale", "") if isinstance(score_b_obj, dict) else ""

            # Average the scores (round to nearest integer)
            if score_a > 0 and score_b > 0:
                avg_score = round((score_a + score_b) / 2)
                combined_rationale = f"[LLM A] {rationale_a}\n\n[LLM B] {rationale_b}"
            elif score_a > 0:
                avg_score = score_a
                combined_rationale = rationale_a
            elif score_b > 0:
                avg_score = score_b
                combined_rationale = rationale_b
            else:
                avg_score = 3  # Default to middle score
                combined_rationale = "평가 점수를 산출할 수 없습니다."

            ensembled["evaluation_scores"][criterion] = {
                "score": avg_score,
                "rationale": combined_rationale,
                "score_a": score_a,
                "score_b": score_b
            }

        print(f"✅ Ensembled results from LLM A and LLM B")
        return ensembled

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

            # Evaluate with LLM(s)
            print(f"🤖 Evaluating application {application.id} ({application.subject})...")
            result_a, result_b = self.evaluate_with_llm(prompt)

            # Ensemble results if both LLMs returned results
            if result_b:
                print(f"🔄 Ensembling results from LLM A and LLM B...")
                result = self._ensemble_results(result_a, result_b)
            else:
                result = result_a

            # Extract results
            ai_category = result.get("ai_category", "분류")
            business_impact = result.get("business_impact", "")
            technical_feasibility = result.get("technical_feasibility", "")
            five_line_summary = result.get("five_line_summary", [])
            evaluation_scores = result.get("evaluation_scores", {})

            # Build AI categories for compatibility
            ai_categories = [{
                "category": ai_category,
                "description": "지원서 기반 AI 요약"
            }]

            # Build evaluation detail with scores
            evaluation_detail = {
                "ai_category": ai_category,
                "business_impact": business_impact,
                "technical_feasibility": technical_feasibility,
                "five_line_summary": five_line_summary,
                "evaluation_scores": evaluation_scores
            }

            # Calculate overall grade from evaluation scores
            if evaluation_scores:
                scores = []
                for criterion in ["innovation", "feasibility", "impact", "clarity"]:
                    if criterion in evaluation_scores and "score" in evaluation_scores[criterion]:
                        scores.append(evaluation_scores[criterion]["score"])

                if scores:
                    avg_score = sum(scores) / len(scores)
                    # Convert average to grade (S/A/B/C/D)
                    if avg_score >= 4.5:
                        overall_grade = "S"
                    elif avg_score >= 3.5:
                        overall_grade = "A"
                    elif avg_score >= 2.5:
                        overall_grade = "B"
                    elif avg_score >= 1.5:
                        overall_grade = "C"
                    else:
                        overall_grade = "D"
                else:
                    overall_grade = "B"  # Default
            else:
                # Fallback to old simple logic if scores not provided
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
