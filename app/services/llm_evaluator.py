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
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
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

    def _print_prompt(self, llm_name: str, prompt: str, step: str = ""):
        """Print prompt to terminal for debugging"""
        separator = "=" * 80
        print(f"\n{separator}")
        print(f"🎯 {llm_name} PROMPT {step}")
        print(f"{separator}")
        print(prompt)
        print(f"{separator}\n")

    def _print_response(self, llm_name: str, content: str, step: str = ""):
        """Print response to terminal for debugging"""
        separator = "=" * 80
        print(f"\n{separator}")
        print(f"💬 {llm_name} RESPONSE {step}")
        print(f"{separator}")
        print(content)
        print(f"{separator}\n")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(Exception)
    )
    def evaluate_with_single_llm(self, llm, prompt: str, llm_name: str = "LLM", step: str = "", verbose: bool = True) -> Dict[str, Any]:
        """
        Evaluate application using a single LLM with robust JSON parsing

        Args:
            llm: LLM instance to use
            prompt: Evaluation prompt
            llm_name: Name of LLM for logging
            step: Step description for logging
            verbose: Whether to print prompts and responses

        Returns:
            Evaluation result dictionary

        Raises:
            Exception: If evaluation fails after retries
        """
        # Print prompt if verbose
        if verbose:
            self._print_prompt(llm_name, prompt, step)

        # Apply rate limiting before LLM call
        self.rate_limiter.wait_if_needed()

        response = llm.invoke(prompt)
        content = response.content

        # Print response if verbose
        if verbose:
            self._print_response(llm_name, content, step)

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

    def build_debate_prompt(
        self,
        application: Application,
        criteria_list: List[EvaluationCriteria],
        llm_a_result: Dict[str, Any]
    ) -> str:
        """
        Build debate prompt for LLM B to review and refine LLM A's evaluation

        Args:
            application: Application to evaluate
            criteria_list: List of evaluation criteria
            llm_a_result: LLM A's evaluation result

        Returns:
            Formatted debate prompt string
        """
        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"

        system_prompt = f"""당신은 글로벌 반도체 대기업의 AI 전문가이자 평가 검토자입니다.
조직: {department_info}

역할: 동료 AI 전문가(LLM A)의 평가를 검토하고, 더 나은 평가를 제시합니다.

중요 원칙:
1. LLM A의 평가를 존중하되, 개선이 필요한 부분은 수정
2. 지원서에 작성된 내용만을 기반으로 평가 (할루시네이션 금지)
3. {department_info} 조직의 업무 특성을 고려
4. 점수는 과장하거나 낮추지 말고 객관적으로 평가
5. LLM A와 의견이 다르면 근거를 명확히 제시
"""

        llm_a_summary = json.dumps(llm_a_result, ensure_ascii=False, indent=2)

        debate_prompt = f"""{system_prompt}

---

## 지원서 정보

과제명: {application.subject or 'N/A'}
조직: {department_info}
참여 인원: {application.participant_count or 'N/A'}명

### Pain Point
{application.pain_point or 'N/A'}

### 개선 아이디어
{application.improvement_idea or 'N/A'}

### 기대 효과
{application.expected_effect or 'N/A'}

---

## LLM A의 평가 결과

```json
{llm_a_summary}
```

---

## 요청사항

위 지원서와 LLM A의 평가를 검토하여, **더 나은 평가**를 제시하세요.

### 검토 지침

1. **AI 기술 분류**: LLM A의 선택이 적절한가? 지원서 내용과 일치하는가?

2. **평가 점수**: 각 기준별 점수가 지원서 내용을 정확히 반영하는가?
   - 너무 관대하거나 엄격하지 않은가?
   - 근거가 명확한가?

3. **개선점**:
   - LLM A가 놓친 중요한 내용은?
   - 과장되거나 과소평가된 부분은?
   - 더 구체적인 근거를 제시할 수 있는가?

### 응답 형식 (JSON)

**CRITICAL**: 반드시 아래 JSON 형식으로만 응답하세요.

```json
{{
  "ai_category": "예측",
  "business_impact": "조직 관점의 경영효과를 2-3문장으로 요약 (LLM A 개선)",
  "technical_feasibility": "AI 관점의 구현 가능성을 2-3문장으로 평가 (LLM A 개선)",
  "five_line_summary": [
    "1. 과제 목적",
    "2. 현재 문제",
    "3. 해결 방안",
    "4. 기대 효과",
    "5. 구현 계획"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }},
  "debate_summary": "LLM A의 평가와 비교하여 어떤 점을 개선했는지 2-3문장으로 설명"
}}
```

**중요 규칙:**
1. **유효한 JSON 형식 필수**
2. **ai_category는 정확히 하나**: "예측", "분류", "챗봇", "에이전트", "최적화", "강화학습" 중 선택
3. **evaluation_scores의 각 score는 1-5 사이의 정수**
4. **rationale은 지원서에 작성된 내용만 사용** (할루시네이션 금지)
5. **LLM A와 점수가 다르면 debate_summary에 이유 설명**
6. **JSON 내부에서 줄바꿈이 필요하면 \\n 사용**
7. **응답은 JSON만 포함하세요**
"""
        return debate_prompt

    def build_final_evaluation_prompt(
        self,
        application: Application,
        criteria_list: List[EvaluationCriteria],
        llm_a_result: Dict[str, Any],
        llm_b_result: Dict[str, Any]
    ) -> str:
        """
        Build final evaluation prompt for LLM A to consider LLM B's review

        Args:
            application: Application to evaluate
            criteria_list: List of evaluation criteria
            llm_a_result: LLM A's initial evaluation
            llm_b_result: LLM B's review and refinement

        Returns:
            Formatted final evaluation prompt
        """
        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"

        system_prompt = f"""당신은 글로벌 반도체 대기업의 AI 전문가입니다.
조직: {department_info}

역할: 당신의 초기 평가와 동료 평가자(LLM B)의 검토를 종합하여 최종 평가를 내립니다.

중요 원칙:
1. 당신의 초기 평가와 LLM B의 검토를 모두 고려
2. LLM B의 지적이 타당하면 수용하고, 그렇지 않으면 근거를 제시하며 원래 평가 유지
3. 지원서에 작성된 내용만을 기반으로 판단 (할루시네이션 금지)
4. 최종 평가는 가장 객관적이고 공정한 결과가 되어야 함
5. {department_info} 조직의 업무 특성을 고려
"""

        llm_a_summary = json.dumps(llm_a_result, ensure_ascii=False, indent=2)
        llm_b_summary = json.dumps(llm_b_result, ensure_ascii=False, indent=2)

        final_prompt = f"""{system_prompt}

---

## 지원서 정보

과제명: {application.subject or 'N/A'}
조직: {department_info}

### Pain Point
{application.pain_point or 'N/A'}

### 개선 아이디어
{application.improvement_idea or 'N/A'}

### 기대 효과
{application.expected_effect or 'N/A'}

---

## 평가 과정

### 1단계: 당신의 초기 평가 (LLM A)

```json
{llm_a_summary}
```

### 2단계: 동료 평가자의 검토 (LLM B)

```json
{llm_b_summary}
```

---

## 최종 평가 요청

위 평가 과정을 검토하여 **최종 평가**를 내려주세요.

### 검토 사항

1. **LLM B의 지적이 타당한가?**
   - 지원서 내용을 더 정확히 반영했는가?
   - 놓친 중요한 내용을 발견했는가?
   - 점수 조정이 합리적인가?

2. **당신의 초기 평가를 유지할 부분은?**
   - LLM B가 과장하거나 잘못 해석한 부분은?
   - 초기 평가가 더 객관적이었던 부분은?

3. **최종 판단**
   - 각 평가 기준별로 최종 점수와 근거 결정
   - 두 평가를 종합한 균형잡힌 결과 도출

### 응답 형식 (JSON)

**CRITICAL**: 반드시 아래 JSON 형식으로만 응답하세요.

```json
{{
  "ai_category": "예측",
  "business_impact": "조직 관점의 경영효과 (최종 판단)",
  "technical_feasibility": "AI 관점의 구현 가능성 (최종 판단)",
  "five_line_summary": [
    "1. 과제 목적",
    "2. 현재 문제",
    "3. 해결 방안",
    "4. 기대 효과",
    "5. 구현 계획"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }},
  "final_decision": "초기 평가와 검토 의견을 종합한 최종 판단 근거를 2-3문장으로 설명"
}}
```

**중요 규칙:**
1. **유효한 JSON 형식 필수**
2. **ai_category는 정확히 하나**: "예측", "분류", "챗봇", "에이전트", "최적화", "강화학습" 중 선택
3. **evaluation_scores의 각 score는 1-5 사이의 정수**
4. **rationale은 최종 판단 근거를 명확히 작성**
5. **final_decision에 초기 평가와 검토 의견을 어떻게 종합했는지 설명**
6. **JSON 내부에서 줄바꿈이 필요하면 \\n 사용**
7. **응답은 JSON만 포함하세요**
"""
        return final_prompt

    def evaluate_with_llm(self, prompt: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Evaluate application using LLM(s) with debate mode
        If both LLMs available: LLM A evaluates first, then LLM B reviews and refines

        Args:
            prompt: Evaluation prompt

        Returns:
            Tuple of (primary_result, secondary_result or None)

        Raises:
            Exception: If evaluation fails after retries
        """
        # Evaluate with primary LLM (A)
        result_a = self.evaluate_with_single_llm(self.llm_a, prompt, "LLM A")

        # If LLM B available, use debate mode
        result_b = None
        if self.llm_b:
            try:
                # LLM B reviews LLM A's evaluation
                print(f"🔄 Starting debate mode: LLM B reviewing LLM A's evaluation...")

                # Extract application and criteria from context (need to pass them)
                # For now, use the same prompt - will be improved in evaluate_application
                result_b = self.evaluate_with_single_llm(self.llm_b, prompt, "LLM B (Initial)")
                print(f"✅ Debate mode: LLM B provided refined evaluation")
            except Exception as e:
                print(f"⚠️  LLM B evaluation failed: {e}")
                print(f"ℹ️  Continuing with LLM A result only")

        return result_a, result_b

    def evaluate_with_multiturn_debate(
        self,
        application: Application,
        criteria_list: List[EvaluationCriteria]
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Evaluate using 3-step debate mode with multiturn conversation for LLM A
        LLM A maintains conversation context across Step 1 and Step 3

        Args:
            application: Application to evaluate
            criteria_list: Evaluation criteria

        Returns:
            Tuple of (llm_a_initial, llm_b_review, llm_a_final or None)
        """
        print(f"\n{'='*80}")
        print(f"🎭 Starting 3-Step Multiturn Debate Mode")
        print(f"{'='*80}\n")

        # Message history for LLM A's multiturn conversation
        llm_a_messages = []

        # Step 1: LLM A's initial evaluation
        print(f"📍 STEP 1/3: LLM A - Initial Evaluation (Multiturn Start)")

        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"

        system_message = f"""당신은 글로벌 반도체 대기업의 AI 전문가입니다.
조직: {department_info}

역할: 지원서 내용을 객관적으로 요약하고 분석합니다.

중요 원칙:
1. 지원서에 작성된 내용만을 기반으로 요약 (할루시네이션 금지)
2. {department_info} 조직의 업무 특성을 고려한 해석
3. 사실 기반의 객관적 분석
4. 과장하거나 추측하지 말 것

**중요**: 곧 동료 평가자(LLM B)가 당신의 평가를 검토할 것입니다.
그 후 LLM B의 의견을 듣고 최종 평가를 조정할 기회가 주어집니다."""

        prompt_a_initial = self.build_evaluation_prompt(application, criteria_list)

        llm_a_messages.append(SystemMessage(content=system_message))
        llm_a_messages.append(HumanMessage(content=prompt_a_initial))

        # Print and invoke
        self._print_prompt("LLM A", system_message + "\n\n" + prompt_a_initial, "[Step 1/3: Initial Evaluation - Multiturn]")

        self.rate_limiter.wait_if_needed()
        response_a_initial = self.llm_a.invoke(llm_a_messages)
        content_a_initial = response_a_initial.content

        self._print_response("LLM A", content_a_initial, "[Step 1/3: Initial Evaluation]")

        # Parse Step 1 result
        json_text_a_initial = self._extract_json_from_text(content_a_initial)
        try:
            result_a_initial = json.loads(json_text_a_initial)
            print(f"✅ LLM A Step 1 JSON parsed successfully")
        except json.JSONDecodeError as e:
            print(f"❌ LLM A Step 1 JSON parsing error: {e}")
            raise

        # Add LLM A's response to message history
        llm_a_messages.append(AIMessage(content=content_a_initial))

        # Step 2: LLM B reviews and refines
        result_b_review = None
        result_a_final = None

        if self.llm_b:
            try:
                print(f"\n📍 STEP 2/3: LLM B - Review & Refinement (Independent)")
                debate_prompt = self.build_debate_prompt(application, criteria_list, result_a_initial)
                result_b_review = self.evaluate_with_single_llm(
                    self.llm_b,
                    debate_prompt,
                    "LLM B",
                    step="[Step 2/3: Review]",
                    verbose=True
                )

                # Step 3: LLM A receives LLM B's feedback in same conversation
                print(f"\n📍 STEP 3/3: LLM A - Final Decision (Multiturn Continue)")

                llm_b_summary = json.dumps(result_b_review, ensure_ascii=False, indent=2)

                feedback_prompt = f"""이제 동료 평가자(LLM B)가 당신의 평가를 검토했습니다.

## LLM B의 검토 의견:

```json
{llm_b_summary}```

## 최종 평가 요청

LLM B의 검토 의견을 고려하여 최종 평가를 내려주세요.

### 검토 사항

1. **LLM B의 지적이 타당한가?**
   - 지원서 내용을 더 정확히 반영했는가?
   - 놓친 중요한 내용을 발견했는가?
   - 점수 조정이 합리적인가?

2. **당신의 초기 평가를 유지할 부분은?**
   - LLM B가 과장하거나 잘못 해석한 부분은?
   - 초기 평가가 더 객관적이었던 부분은?

3. **최종 판단**
   - 각 평가 기준별로 최종 점수와 근거 결정
   - 두 평가를 종합한 균형잡힌 결과 도출

### 응답 형식 (JSON)

**CRITICAL**: 반드시 아래 JSON 형식으로만 응답하세요.

```json
{{
  "ai_category": "예측",
  "business_impact": "조직 관점의 경영효과 (최종 판단)",
  "technical_feasibility": "AI 관점의 구현 가능성 (최종 판단)",
  "five_line_summary": [
    "1. 과제 목적",
    "2. 현재 문제",
    "3. 해결 방안",
    "4. 기대 효과",
    "5. 구현 계획"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }},
  "final_decision": "초기 평가와 LLM B의 검토 의견을 종합한 최종 판단 근거를 2-3문장으로 설명"
}}
```

**중요**:
- LLM B의 의견에 동의하면 점수를 조정하고 이유 설명
- LLM B의 의견에 동의하지 않으면 초기 평가를 유지하고 이유 설명
- 부분적으로 동의하면 절충안 제시"""

                llm_a_messages.append(HumanMessage(content=feedback_prompt))

                # Print and invoke
                self._print_prompt("LLM A", feedback_prompt, "[Step 3/3: Final Decision - Multiturn]")

                self.rate_limiter.wait_if_needed()
                response_a_final = self.llm_a.invoke(llm_a_messages)
                content_a_final = response_a_final.content

                self._print_response("LLM A", content_a_final, "[Step 3/3: Final Decision]")

                # Parse Step 3 result
                json_text_a_final = self._extract_json_from_text(content_a_final)
                try:
                    result_a_final = json.loads(json_text_a_final)
                    print(f"✅ LLM A Step 3 JSON parsed successfully")
                except json.JSONDecodeError as e:
                    print(f"❌ LLM A Step 3 JSON parsing error: {e}")
                    raise

                print(f"\n{'='*80}")
                print(f"✅ 3-Step Multiturn Debate Completed")
                print(f"  - LLM A maintained conversation context across Step 1 and Step 3")
                print(f"  - Total messages in LLM A conversation: {len(llm_a_messages) + 1}")
                print(f"{'='*80}\n")

            except Exception as e:
                print(f"⚠️  Debate process failed at step 2 or 3: {e}")
                import traceback
                traceback.print_exc()
                print(f"ℹ️  Using LLM A initial result only")

        return result_a_initial, result_b_review, result_a_final
    
    def _merge_debate_results(
        self,
        result_a_initial: Dict[str, Any],
        result_b_review: Optional[Dict[str, Any]],
        result_a_final: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge 3-step debate results: Use LLM A's final decision as primary

        Args:
            result_a_initial: LLM A's initial evaluation
            result_b_review: LLM B's review (optional)
            result_a_final: LLM A's final decision after considering B's review (optional)

        Returns:
            Merged result dictionary with all three perspectives
        """
        # If we have final decision from LLM A, use it as primary
        if result_a_final:
            merged = {
                "ai_category": result_a_final.get("ai_category", result_a_initial.get("ai_category", "분류")),
                "business_impact": result_a_final.get("business_impact", result_a_initial.get("business_impact", "")),
                "technical_feasibility": result_a_final.get("technical_feasibility", result_a_initial.get("technical_feasibility", "")),
                "five_line_summary": result_a_final.get("five_line_summary", result_a_initial.get("five_line_summary", [])),
                "debate_summary": result_a_final.get("final_decision", result_b_review.get("debate_summary", "") if result_b_review else ""),
                "evaluation_scores": {}
            }

            # Merge evaluation scores with all three perspectives
            scores_a_initial = result_a_initial.get("evaluation_scores", {})
            scores_b_review = result_b_review.get("evaluation_scores", {}) if result_b_review else {}
            scores_a_final = result_a_final.get("evaluation_scores", {})

            # Get all criteria keys
            all_criteria = set(scores_a_initial.keys()) | set(scores_b_review.keys()) | set(scores_a_final.keys())

            for criterion in all_criteria:
                score_a_init_obj = scores_a_initial.get(criterion, {})
                score_b_rev_obj = scores_b_review.get(criterion, {})
                score_a_final_obj = scores_a_final.get(criterion, {})

                score_a_init = score_a_init_obj.get("score", 0) if isinstance(score_a_init_obj, dict) else 0
                score_b_rev = score_b_rev_obj.get("score", 0) if isinstance(score_b_rev_obj, dict) else 0
                score_a_final = score_a_final_obj.get("score", 0) if isinstance(score_a_final_obj, dict) else 0

                rationale_a_init = score_a_init_obj.get("rationale", "") if isinstance(score_a_init_obj, dict) else ""
                rationale_b_rev = score_b_rev_obj.get("rationale", "") if isinstance(score_b_rev_obj, dict) else ""
                rationale_a_final = score_a_final_obj.get("rationale", "") if isinstance(score_a_final_obj, dict) else ""

                # Use LLM A's final score as primary
                final_score = score_a_final if score_a_final > 0 else (score_a_init if score_a_init > 0 else 3)

                # Build comprehensive rationale showing all three steps
                rationale_parts = []
                if score_a_init > 0:
                    rationale_parts.append(f"[Step 1 - LLM A 초기: {score_a_init}점]\n{rationale_a_init}")
                if score_b_rev > 0:
                    rationale_parts.append(f"[Step 2 - LLM B 검토: {score_b_rev}점]\n{rationale_b_rev}")
                if score_a_final > 0:
                    rationale_parts.append(f"[Step 3 - LLM A 최종: {score_a_final}점]\n{rationale_a_final}")

                combined_rationale = "\n\n".join(rationale_parts) if rationale_parts else "평가 점수를 산출할 수 없습니다."

                merged["evaluation_scores"][criterion] = {
                    "score": final_score,
                    "rationale": combined_rationale,
                    "score_a_initial": score_a_init,
                    "score_b_review": score_b_rev,
                    "score_a_final": score_a_final
                }

            print(f"✅ Merged 3-step debate results: LLM A's final decision with full context")
            return merged

        # Fallback to 2-step if no final decision
        elif result_b_review:
            return self._merge_2step_results(result_a_initial, result_b_review)

        # Fallback to initial result if debate failed
        else:
            return result_a_initial

    def _merge_2step_results(self, result_a: Dict[str, Any], result_b: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback: Merge 2-step results (for backward compatibility)"""
        merged = {
            "ai_category": result_b.get("ai_category", result_a.get("ai_category", "분류")),
            "business_impact": result_b.get("business_impact", result_a.get("business_impact", "")),
            "technical_feasibility": result_b.get("technical_feasibility", result_a.get("technical_feasibility", "")),
            "five_line_summary": result_b.get("five_line_summary", result_a.get("five_line_summary", [])),
            "debate_summary": result_b.get("debate_summary", ""),
            "evaluation_scores": {}
        }

        scores_a = result_a.get("evaluation_scores", {})
        scores_b = result_b.get("evaluation_scores", {})
        all_criteria = set(scores_a.keys()) | set(scores_b.keys())

        for criterion in all_criteria:
            score_a_obj = scores_a.get(criterion, {})
            score_b_obj = scores_b.get(criterion, {})

            score_a = score_a_obj.get("score", 0) if isinstance(score_a_obj, dict) else 0
            score_b = score_b_obj.get("score", 0) if isinstance(score_b_obj, dict) else 0

            rationale_a = score_a_obj.get("rationale", "") if isinstance(score_a_obj, dict) else ""
            rationale_b = score_b_obj.get("rationale", "") if isinstance(score_b_obj, dict) else ""

            final_score = score_b if score_b > 0 else (score_a if score_a > 0 else 3)

            if score_a > 0 and score_b > 0 and score_a != score_b:
                combined_rationale = f"[LLM A 초기: {score_a}점]\n{rationale_a}\n\n[LLM B 검토: {score_b}점]\n{rationale_b}"
            elif score_b > 0:
                combined_rationale = f"[합의: {score_b}점]\n{rationale_b}"
            else:
                combined_rationale = rationale_a

            merged["evaluation_scores"][criterion] = {
                "score": final_score,
                "rationale": combined_rationale,
                "score_a": score_a,
                "score_b": score_b
            }

        return merged

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
            
            # Evaluate with LLM(s)
            print(f"🤖 Evaluating application {application.id} ({application.subject})...")

            if self.llm_b:
                # 3-Step Multiturn Debate mode: LLM A → LLM B → LLM A (with conversation context)
                print(f"💬 Using 3-step multiturn debate mode: LLM A (multiturn) → LLM B → LLM A (continue conversation)")
                result_a_initial, result_b_review, result_a_final = self.evaluate_with_multiturn_debate(
                    application,
                    criteria_list or []
                )

                # Merge results
                result = self._merge_debate_results(result_a_initial, result_b_review, result_a_final)
            else:
                # Single LLM mode
                print(f"🤖 Using single LLM mode")
                prompt = self.build_evaluation_prompt(application, criteria_list or [])
                result_a = self.evaluate_with_single_llm(
                    self.llm_a,
                    prompt,
                    "LLM A",
                    step="[Single LLM Mode]"
                )
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
