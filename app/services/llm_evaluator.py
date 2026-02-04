"""
LLM Evaluator Service
Enhanced with:
- English prompts with Korean responses
- Token usage tracking and logging
- Evaluation quality validation
- Weighted scoring support
- Improved retry logic
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
from app.models.category import AICategory
from app.services.rate_limiter import RateLimiter


class EvaluationQualityError(Exception):
    """Raised when evaluation quality validation fails"""
    pass


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

        # Token usage tracking
        self.token_usage = {
            "llm_a": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0},
            "llm_b": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0}
        }

        # Criteria name to key mapping (한글 -> 영문)
        self.criteria_key_map = {
            "혁신성": "innovation",
            "실현가능성": "feasibility",
            "효과성": "impact",
            "명확성": "clarity"
        }

    def _log_token_usage(self, llm_name: str, response: Any) -> None:
        """
        Log token usage from LLM response

        Args:
            llm_name: "llm_a" or "llm_b"
            response: LLM response object with usage_metadata
        """
        try:
            if hasattr(response, 'response_metadata') and 'token_usage' in response.response_metadata:
                usage = response.response_metadata['token_usage']
                self.token_usage[llm_name]["prompt_tokens"] += usage.get('prompt_tokens', 0)
                self.token_usage[llm_name]["completion_tokens"] += usage.get('completion_tokens', 0)
                self.token_usage[llm_name]["total_tokens"] += usage.get('total_tokens', 0)
                self.token_usage[llm_name]["api_calls"] += 1

                print(f"  📊 {llm_name.upper()} Token Usage: "
                      f"Prompt={usage.get('prompt_tokens', 0)}, "
                      f"Completion={usage.get('completion_tokens', 0)}, "
                      f"Total={usage.get('total_tokens', 0)}")
        except Exception as e:
            print(f"  ⚠️  Failed to log token usage: {e}")

    def get_token_usage_summary(self) -> Dict[str, Any]:
        """
        Get summary of token usage across all LLMs

        Returns:
            Dictionary with token usage statistics
        """
        total = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_calls": 0
        }

        for llm_data in self.token_usage.values():
            total["prompt_tokens"] += llm_data["prompt_tokens"]
            total["completion_tokens"] += llm_data["completion_tokens"]
            total["total_tokens"] += llm_data["total_tokens"]
            total["api_calls"] += llm_data["api_calls"]

        return {
            "llm_a": self.token_usage["llm_a"].copy(),
            "llm_b": self.token_usage["llm_b"].copy(),
            "total": total
        }

    def reset_token_usage(self) -> None:
        """Reset token usage counters"""
        for llm_name in self.token_usage:
            self.token_usage[llm_name] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "api_calls": 0
            }

    def _validate_evaluation_quality(
        self,
        result: Dict[str, Any],
        criteria_list: List[EvaluationCriteria],
        valid_categories: List[str]
    ) -> None:
        """
        Validate quality of LLM evaluation result

        Args:
            result: Evaluation result to validate
            criteria_list: Expected evaluation criteria
            valid_categories: List of valid AI category names from database

        Raises:
            EvaluationQualityError: If validation fails
        """
        # Check required fields
        required_fields = ["ai_category", "business_impact", "technical_feasibility",
                          "five_line_summary", "evaluation_scores"]
        for field in required_fields:
            if field not in result or not result[field]:
                raise EvaluationQualityError(f"Missing or empty required field: {field}")

        # Validate ai_category against database categories
        if result["ai_category"] not in valid_categories:
            raise EvaluationQualityError(
                f"Invalid AI category: {result['ai_category']}. Must be one of {valid_categories}"
            )

        # Validate five_line_summary
        if not isinstance(result["five_line_summary"], list) or len(result["five_line_summary"]) != 5:
            raise EvaluationQualityError(
                f"five_line_summary must be a list of 5 items, got {len(result.get('five_line_summary', []))}"
            )

        # Validate evaluation_scores
        scores = result["evaluation_scores"]
        if not isinstance(scores, dict):
            raise EvaluationQualityError("evaluation_scores must be a dictionary")

        for criterion in criteria_list:
            key = self.criteria_key_map.get(criterion.name, criterion.name)
            if key not in scores:
                raise EvaluationQualityError(f"Missing score for criterion: {key}")

            score_data = scores[key]
            if not isinstance(score_data, dict):
                raise EvaluationQualityError(f"Score data for {key} must be a dictionary")

            if "score" not in score_data or "rationale" not in score_data:
                raise EvaluationQualityError(f"Score data for {key} missing 'score' or 'rationale'")

            score = score_data["score"]
            if not isinstance(score, (int, float)) or not (1 <= score <= 5):
                raise EvaluationQualityError(f"Score for {key} must be between 1 and 5, got {score}")

            rationale = score_data["rationale"]
            if not isinstance(rationale, str) or len(rationale) < 10:
                raise EvaluationQualityError(
                    f"Rationale for {key} must be a string with at least 10 characters"
                )

        print(f"  ✅ Evaluation quality validation passed")

    def _get_valid_category_names(self, ai_categories: Optional[List[AICategory]]) -> str:
        """
        Get valid category names as comma-separated string

        Args:
            ai_categories: List of AI categories from database (optional)

        Returns:
            Comma-separated string of category names (e.g., '"예측", "분류", "챗봇"')
        """
        if not ai_categories:
            return '"예측", "분류", "챗봇", "에이전트", "최적화", "강화학습"'

        names = [f'"{cat.name}"' for cat in ai_categories]
        return ", ".join(names)

    def _build_ai_category_list(self, ai_categories: Optional[List[AICategory]]) -> str:
        """
        Build AI category list from database categories

        Args:
            ai_categories: List of AI categories from database (optional)

        Returns:
            Formatted AI category list string
        """
        if not ai_categories:
            # Fallback to default categories
            return """- **예측 (Prediction)**: Future value prediction, demand forecasting, trend analysis
- **분류 (Classification)**: Image/text classification, defect detection, category classification
- **챗봇 (Chatbot)**: Conversational interface, auto-response, Q&A
- **에이전트 (Agent)**: Autonomous decision-making, complex task automation, workflow automation
- **최적화 (Optimization)**: Resource optimization, scheduling, route optimization
- **강화학습 (Reinforcement Learning)**: Learning-based decision-making, simulation optimization"""

        category_lines = []
        for cat in ai_categories:
            description = cat.description or "No description available"
            category_lines.append(f"- **{cat.name}**: {description}")

        return "\n".join(category_lines)

    def _build_criteria_guide(self, criteria_list: List[EvaluationCriteria]) -> str:
        """
        Build evaluation criteria guide from database criteria (English)

        Args:
            criteria_list: List of evaluation criteria from DB

        Returns:
            Formatted criteria guide string in English
        """
        if not criteria_list:
            # Fallback to default if no criteria
            return """
**Innovation**: Creativity and novelty of AI technology (1-5 points)
**Feasibility**: Technical implementation difficulty and team capability (1-5 points)
**Impact**: Business impact on the organization (1-5 points)
**Clarity**: Specificity of problem definition and solution approach (1-5 points)
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
      "score": "integer between 1-5",
      "rationale": "{criteria.name} evaluation rationale (2-3 sentences, based on application, IN KOREAN)"
    }}''')

        return ",\n".join(json_parts)

    def build_evaluation_prompt(
        self,
        application: Application,
        criteria_list: List[EvaluationCriteria],
        ai_categories: Optional[List[AICategory]] = None
    ) -> str:
        """
        Build evaluation prompt for LLM

        Args:
            application: Application to evaluate
            criteria_list: List of evaluation criteria
            ai_categories: List of valid AI categories from database (optional)

        Returns:
            Formatted prompt string
        """
        # Build department information
        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"

        system_prompt = f"""You are an AI expert at a global semiconductor company.
Organization: {department_info}

Role: Objectively summarize and analyze application content.

Important Principles:
1. Base summaries only on what is written in the application (no hallucination)
2. Consider the work characteristics of {department_info} organization
3. Fact-based objective analysis
4. Do not exaggerate or speculate

**IMPORTANT: Please provide your entire response in Korean language.**
"""

        app_info = f"""
# AI Project Application Evaluation

## Project Basic Information
- Project Title: {application.subject or 'N/A'}
- Organization: {department_info}
- Participants: {application.participant_count or 'N/A'} people
- Representative: {application.representative_name or 'N/A'}

## Application Content
### Current Work
{application.current_work or 'N/A'}

### Pain Point (Problem to Solve)
{application.pain_point or 'N/A'}

### Improvement Idea
{application.improvement_idea or 'N/A'}

### Expected Effect
{application.expected_effect or 'N/A'}

### Hopes/Expectations
{application.hope or 'N/A'}

## Pre-Survey
{json.dumps(application.pre_survey, ensure_ascii=False, indent=2) if application.pre_survey else 'N/A'}

## Participant Technical Capabilities
{json.dumps(application.tech_capabilities, ensure_ascii=False, indent=2) if application.tech_capabilities else 'N/A'}

---

## Evaluation Request

Based on the application content, summarize and evaluate the following:

### 1. AI Technology Classification
Select **exactly one** AI technology from the application:
{self._build_ai_category_list(ai_categories)}

### 2. Business Impact from Organization Perspective
Summarize the business impact of this project from {department_info} organization's perspective (2-3 sentences in Korean):
- Based only on the expected effects written in the application
- No speculation or exaggeration

### 3. Technical Feasibility from AI Perspective
Evaluate implementation feasibility based on application content (participants, technical skills, data, etc.) (2-3 sentences in Korean):
- Refer only to content written in the application
- Objectively assess technical difficulty, data availability, team capability, etc.

### 4. 5-Line Summary of Entire Application
Summarize the core content of this application in 5 lines (in Korean):
1. Project purpose (1 line)
2. Current problem (1 line)
3. Solution approach (1 line)
4. Expected effect (1 line)
5. Implementation plan (1 line)

### 5. Scoring and Rationale by Evaluation Criteria (5-point scale)
Evaluate the application based on the following criteria, providing a 1-5 score and 2-3 sentence rationale for each (in Korean):

{self._build_criteria_guide(criteria_list)}
"""

        prompt = f"""{system_prompt}

{app_info}

---

## Response Format (JSON)
**CRITICAL**: You must respond in ONLY the JSON format below. Do not include any other text.

```json
{{
  "ai_category": "예측",
  "business_impact": "Summarize business impact from organization perspective in 2-3 sentences (IN KOREAN)",
  "technical_feasibility": "Evaluate technical feasibility from AI perspective in 2-3 sentences (IN KOREAN)",
  "five_line_summary": [
    "1. Project purpose (IN KOREAN)",
    "2. Current problem (IN KOREAN)",
    "3. Solution approach (IN KOREAN)",
    "4. Expected effect (IN KOREAN)",
    "5. Implementation plan (IN KOREAN)"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }}
}}
```

**Important Rules:**
1. **Valid JSON format required** - All strings must be enclosed in double quotes (")
2. **ai_category must be exactly one of**: {self._get_valid_category_names(ai_categories)}
3. **Each score in evaluation_scores must be an integer between 1-5**
4. **All rationale must use only content written in the application** (no hallucination)
5. **Use \\n for line breaks within JSON**
6. **No comma (,) after the last item** - Must comply with JSON syntax
7. **Close all curly braces and brackets correctly**
8. Consider {department_info} organization characteristics

**IMPORTANT: Respond with ONLY the JSON object. No explanations or additional text. All Korean text content must be in Korean language.**
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
    def _normalize_evaluation_result(self, result: Dict[str, Any], llm_name: str = "LLM") -> Dict[str, Any]:
        """
        Normalize LLM evaluation result structure.

        Some LLMs (especially LLM B) may return evaluation criteria directly at top level
        instead of wrapping them in "evaluation_scores". This function fixes that.

        Expected format:
        {
            "ai_category": "...",
            "business_impact": "...",
            "evaluation_scores": {
                "참여자 역량": {"score": 3, "rationale": "..."}
            }
        }

        Incorrect format (LLM B sometimes does this):
        {
            "참여자 역량": {"score": 3, "rationale": "..."},
            "실현가능성": {"score": 4, "rationale": "..."}
            // missing evaluation_scores wrapper!
        }

        Args:
            result: Raw result from LLM
            llm_name: Name of LLM for logging

        Returns:
            Normalized result with evaluation_scores structure
        """
        # If evaluation_scores already exists, structure is correct
        if "evaluation_scores" in result:
            return result

        print(f"⚠️  {llm_name}: evaluation_scores not found, attempting to normalize structure...")

        # Find criteria-like keys (dict with "score" field)
        evaluation_scores = {}
        other_fields = {}

        for key, value in result.items():
            # Check if this looks like an evaluation criterion
            if isinstance(value, dict) and "score" in value:
                evaluation_scores[key] = value
                print(f"   Found criterion: {key}")
            else:
                other_fields[key] = value

        if evaluation_scores:
            # Reconstruct with proper structure
            normalized = {
                "ai_category": other_fields.get("ai_category", "분류"),
                "business_impact": other_fields.get("business_impact", ""),
                "technical_feasibility": other_fields.get("technical_feasibility", ""),
                "five_line_summary": other_fields.get("five_line_summary", []),
                "evaluation_scores": evaluation_scores
            }

            # Add any extra fields
            for key in ["debate_summary", "final_decision"]:
                if key in other_fields:
                    normalized[key] = other_fields[key]

            print(f"✅ {llm_name}: Normalized structure with {len(evaluation_scores)} criteria")
            return normalized
        else:
            print(f"⚠️  {llm_name}: No evaluation criteria found, returning original result")
            return result

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

        # Log token usage
        token_key = "llm_a" if "LLM A" in llm_name else "llm_b"
        self._log_token_usage(token_key, response)

        # Print response if verbose
        if verbose:
            self._print_response(llm_name, content, step)

        # Extract JSON from response
        json_text = self._extract_json_from_text(content)

        # Parse JSON with retry on quality failure
        try:
            result = json.loads(json_text)
            print(f"✅ {llm_name} JSON parsed successfully")

            # Normalize structure: Fix LLM B's incorrect format
            result = self._normalize_evaluation_result(result, llm_name)

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
        llm_a_result: Dict[str, Any],
        ai_categories: Optional[List[AICategory]] = None
    ) -> str:
        """
        Build debate prompt for LLM B to review and refine LLM A's evaluation

        Args:
            application: Application to evaluate
            criteria_list: List of evaluation criteria
            llm_a_result: LLM A's evaluation result
            ai_categories: List of valid AI categories from database (optional)

        Returns:
            Formatted debate prompt string
        """
        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"

        system_prompt = f"""You are an AI expert and evaluation reviewer at a global semiconductor company.
Organization: {department_info}

Role: Review the evaluation from colleague AI expert (LLM A) and provide a better evaluation.

Important Principles:
1. Respect LLM A's evaluation, but correct areas that need improvement
2. Base evaluation only on what is written in the application (no hallucination)
3. Consider the work characteristics of {department_info} organization
4. Evaluate scores objectively without exaggeration or underestimation
5. If opinion differs from LLM A, provide clear rationale

**IMPORTANT: Please provide your entire response in Korean language.**
"""

        llm_a_summary = json.dumps(llm_a_result, ensure_ascii=False, indent=2)

        debate_prompt = f"""{system_prompt}

---

## Application Information

Project Title: {application.subject or 'N/A'}
Organization: {department_info}
Participants: {application.participant_count or 'N/A'} people

### Pain Point
{application.pain_point or 'N/A'}

### Improvement Idea
{application.improvement_idea or 'N/A'}

### Expected Effect
{application.expected_effect or 'N/A'}

---

## LLM A's Evaluation Result

```json
{llm_a_summary}
```

---

## Request

Review the above application and LLM A's evaluation, and provide a **better evaluation**.

### Review Guidelines

1. **AI Technology Classification**: Is LLM A's choice appropriate? Does it match the application content?

2. **Evaluation Scores**: Do the scores for each criterion accurately reflect the application content?
   - Are they too lenient or too strict?
   - Is the rationale clear?

3. **Improvements**:
   - What important content did LLM A miss?
   - Are there exaggerated or underestimated parts?
   - Can you provide more specific rationale?

### Response Format (JSON)

**CRITICAL**: You must respond in ONLY the JSON format below.

```json
{{
  "ai_category": "예측",
  "business_impact": "Summarize business impact from organization perspective in 2-3 sentences (improving on LLM A) (IN KOREAN)",
  "technical_feasibility": "Evaluate technical feasibility from AI perspective in 2-3 sentences (improving on LLM A) (IN KOREAN)",
  "five_line_summary": [
    "1. Project purpose (IN KOREAN)",
    "2. Current problem (IN KOREAN)",
    "3. Solution approach (IN KOREAN)",
    "4. Expected effect (IN KOREAN)",
    "5. Implementation plan (IN KOREAN)"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }},
  "debate_summary": "Explain in 2-3 sentences what improvements were made compared to LLM A's evaluation (IN KOREAN)"
}}
```

**Important Rules:**
1. **Valid JSON format required**
2. **ai_category must be exactly one of**: {self._get_valid_category_names(ai_categories)}
3. **Each score in evaluation_scores must be an integer between 1-5**
4. **rationale must use only content written in the application** (no hallucination)
5. **If score differs from LLM A, explain reason in debate_summary**
6. **Use \\n for line breaks within JSON**
7. **Respond with JSON only**

**IMPORTANT: All Korean text content must be in Korean language.**
"""
        return debate_prompt

    def build_final_evaluation_prompt(
        self,
        application: Application,
        criteria_list: List[EvaluationCriteria],
        llm_a_result: Dict[str, Any],
        llm_b_result: Dict[str, Any],
        ai_categories: Optional[List[AICategory]] = None
    ) -> str:
        """
        Build final evaluation prompt for LLM A to consider LLM B's review

        Args:
            application: Application to evaluate
            criteria_list: List of evaluation criteria
            llm_a_result: LLM A's initial evaluation
            llm_b_result: LLM B's review and refinement
            ai_categories: List of valid AI categories from database (optional)

        Returns:
            Formatted final evaluation prompt
        """
        department_info = f"{application.division or 'N/A'} > {application.department.name if application.department else 'N/A'}"

        system_prompt = f"""You are an AI expert at a global semiconductor company.
Organization: {department_info}

Role: Synthesize your initial evaluation and colleague reviewer (LLM B)'s review to make a final evaluation.

Important Principles:
1. Consider both your initial evaluation and LLM B's review
2. If LLM B's points are valid, accept them; otherwise maintain original evaluation with rationale
3. Base judgment only on what is written in the application (no hallucination)
4. Final evaluation must be the most objective and fair result
5. Consider the work characteristics of {department_info} organization

**IMPORTANT: Please provide your entire response in Korean language.**
"""

        llm_a_summary = json.dumps(llm_a_result, ensure_ascii=False, indent=2)
        llm_b_summary = json.dumps(llm_b_result, ensure_ascii=False, indent=2)

        final_prompt = f"""{system_prompt}

---

## Application Information

Project Title: {application.subject or 'N/A'}
Organization: {department_info}

### Pain Point
{application.pain_point or 'N/A'}

### Improvement Idea
{application.improvement_idea or 'N/A'}

### Expected Effect
{application.expected_effect or 'N/A'}

---

## Evaluation Process

### Step 1: Your Initial Evaluation (LLM A)

```json
{llm_a_summary}
```

### Step 2: Colleague Reviewer's Review (LLM B)

```json
{llm_b_summary}
```

---

## Final Evaluation Request

Review the above evaluation process and provide a **final evaluation**.

### Review Considerations

1. **Are LLM B's points valid?**
   - Did it more accurately reflect the application content?
   - Did it find important content that was missed?
   - Are the score adjustments reasonable?

2. **What parts of your initial evaluation should be maintained?**
   - Did LLM B exaggerate or misinterpret anything?
   - Were there parts where the initial evaluation was more objective?

3. **Final Decision**
   - Determine final score and rationale for each evaluation criterion
   - Derive balanced results synthesizing both evaluations

### Response Format (JSON)

**CRITICAL**: You must respond in ONLY the JSON format below.

```json
{{
  "ai_category": "예측",
  "business_impact": "Business impact from organization perspective (final decision) (IN KOREAN)",
  "technical_feasibility": "Technical feasibility from AI perspective (final decision) (IN KOREAN)",
  "five_line_summary": [
    "1. Project purpose (IN KOREAN)",
    "2. Current problem (IN KOREAN)",
    "3. Solution approach (IN KOREAN)",
    "4. Expected effect (IN KOREAN)",
    "5. Implementation plan (IN KOREAN)"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }},
  "final_decision": "Explain in 2-3 sentences the rationale for final decision synthesizing initial evaluation and review opinion (IN KOREAN)"
}}
```

**Important Rules:**
1. **Valid JSON format required**
2. **ai_category must be exactly one of**: {self._get_valid_category_names(ai_categories)}
3. **Each score in evaluation_scores must be an integer between 1-5**
4. **rationale must clearly state the final decision rationale**
5. **final_decision must explain how initial evaluation and review opinion were synthesized**
6. **Use \\n for line breaks within JSON**
7. **Respond with JSON only**

**IMPORTANT: All Korean text content must be in Korean language.**
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
        criteria_list: List[EvaluationCriteria],
        ai_categories: Optional[List[AICategory]] = None
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Evaluate using 3-step debate mode with multiturn conversation for LLM A
        LLM A maintains conversation context across Step 1 and Step 3

        Args:
            application: Application to evaluate
            criteria_list: Evaluation criteria
            ai_categories: List of valid AI categories from database (optional)

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

        system_message = f"""You are an AI expert at a global semiconductor company.
Organization: {department_info}

Role: Objectively summarize and analyze application content.

Important Principles:
1. Base summaries only on what is written in the application (no hallucination)
2. Consider the work characteristics of {department_info} organization
3. Fact-based objective analysis
4. Do not exaggerate or speculate

**Important**: Soon, colleague reviewer (LLM B) will review your evaluation.
After that, you will have an opportunity to adjust your final evaluation after hearing LLM B's opinion.

**IMPORTANT: Please provide your entire response in Korean language.**"""

        prompt_a_initial = self.build_evaluation_prompt(application, criteria_list, ai_categories)

        llm_a_messages.append(SystemMessage(content=system_message))
        llm_a_messages.append(HumanMessage(content=prompt_a_initial))

        # Print and invoke
        self._print_prompt("LLM A", system_message + "\n\n" + prompt_a_initial, "[Step 1/3: Initial Evaluation - Multiturn]")

        self.rate_limiter.wait_if_needed()
        response_a_initial = self.llm_a.invoke(llm_a_messages)
        content_a_initial = response_a_initial.content

        # Log token usage
        self._log_token_usage("llm_a", response_a_initial)

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
                debate_prompt = self.build_debate_prompt(application, criteria_list, result_a_initial, ai_categories)
                result_b_review = self.evaluate_with_single_llm(
                    self.llm_b,
                    debate_prompt,
                    "LLM B",
                    step="[Step 2/3: Review]",
                    verbose=True
                )

                # Debug: Print LLM B's evaluation_scores
                print(f"\n{'='*80}")
                print(f"🔍 DEBUG: LLM B evaluation_scores")
                print(f"{'='*80}")
                if result_b_review and "evaluation_scores" in result_b_review:
                    for crit, data in result_b_review["evaluation_scores"].items():
                        score = data.get("score", "N/A") if isinstance(data, dict) else "N/A"
                        print(f"  {crit}: score={score}")
                else:
                    print(f"  ⚠️  WARNING: evaluation_scores not found in result_b_review")
                    print(f"  result_b_review keys: {list(result_b_review.keys()) if result_b_review else 'None'}")
                print(f"{'='*80}\n")

                # Step 3: LLM A receives LLM B's feedback in same conversation
                print(f"\n📍 STEP 3/3: LLM A - Final Decision (Multiturn Continue)")

                llm_b_summary = json.dumps(result_b_review, ensure_ascii=False, indent=2)

                feedback_prompt = f"""Now colleague reviewer (LLM B) has reviewed your evaluation.

## LLM B's Review Opinion:

```json
{llm_b_summary}```

## Final Evaluation Request

Please provide a final evaluation considering LLM B's review opinion.

### Review Considerations

1. **Are LLM B's points valid?**
   - Did it more accurately reflect the application content?
   - Did it find important content that was missed?
   - Are the score adjustments reasonable?

2. **What parts of your initial evaluation should be maintained?**
   - Did LLM B exaggerate or misinterpret anything?
   - Were there parts where the initial evaluation was more objective?

3. **Final Decision**
   - Determine final score and rationale for each evaluation criterion
   - Derive balanced results synthesizing both evaluations

### Response Format (JSON)

**CRITICAL**: You must respond in ONLY the JSON format below.

```json
{{
  "ai_category": "예측",
  "business_impact": "Business impact from organization perspective (final decision) (IN KOREAN)",
  "technical_feasibility": "Technical feasibility from AI perspective (final decision) (IN KOREAN)",
  "five_line_summary": [
    "1. Project purpose (IN KOREAN)",
    "2. Current problem (IN KOREAN)",
    "3. Solution approach (IN KOREAN)",
    "4. Expected effect (IN KOREAN)",
    "5. Implementation plan (IN KOREAN)"
  ],
  "evaluation_scores": {{
{self._build_json_format_example(criteria_list)}
  }},
  "final_decision": "Explain in 2-3 sentences the rationale for final decision synthesizing initial evaluation and LLM B's review opinion (IN KOREAN)"
}}
```

**Important**:
- If you agree with LLM B's opinion, adjust score and explain reason
- If you disagree with LLM B's opinion, maintain initial evaluation and explain reason
- If you partially agree, present a compromise

**IMPORTANT: All Korean text content must be in Korean language.**"""

                llm_a_messages.append(HumanMessage(content=feedback_prompt))

                # Print and invoke
                self._print_prompt("LLM A", feedback_prompt, "[Step 3/3: Final Decision - Multiturn]")

                self.rate_limiter.wait_if_needed()
                response_a_final = self.llm_a.invoke(llm_a_messages)
                content_a_final = response_a_final.content

                # Log token usage
                self._log_token_usage("llm_a", response_a_final)

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

            # Debug: Check what we're merging
            print(f"\n{'='*80}")
            print(f"🔍 DEBUG: Merging 3-step debate results")
            print(f"{'='*80}")
            print(f"  scores_a_initial: {len(scores_a_initial)} criteria")
            print(f"  scores_b_review: {len(scores_b_review)} criteria")
            print(f"  scores_a_final: {len(scores_a_final)} criteria")
            if len(scores_b_review) == 0:
                print(f"  ⚠️  WARNING: scores_b_review is EMPTY!")
                print(f"  result_b_review keys: {list(result_b_review.keys()) if result_b_review else 'None'}")
            print(f"{'='*80}\n")

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

    def calculate_weighted_score(
        self,
        evaluation_scores: Dict[str, Any],
        criteria_list: List[EvaluationCriteria]
    ) -> float:
        """
        Calculate weighted average score based on criteria weights

        Args:
            evaluation_scores: Dictionary of evaluation scores
            criteria_list: List of evaluation criteria with weights

        Returns:
            Weighted average score (float)
        """
        total_weighted_score = 0.0
        total_weight = 0.0

        for criterion in criteria_list:
            key = self.criteria_key_map.get(criterion.name, criterion.name.lower())
            if key in evaluation_scores:
                score_data = evaluation_scores[key]
                if isinstance(score_data, dict) and "score" in score_data:
                    score = score_data["score"]
                    weight = getattr(criterion, "weight", 1.0)  # Default weight = 1.0 if not set
                    total_weighted_score += score * weight
                    total_weight += weight

        if total_weight == 0:
            return 0.0

        weighted_avg = total_weighted_score / total_weight
        print(f"  📊 Weighted average score: {weighted_avg:.2f} (total weight: {total_weight})")
        return weighted_avg

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

            # Get valid AI categories from database
            ai_category_objects = db.query(AICategory).filter(
                AICategory.is_active == True
            ).order_by(AICategory.display_order).all()

            if not ai_category_objects:
                # Fallback to default if no categories in DB
                ai_category_objects = None
                valid_categories = ["예측", "분류", "챗봇", "에이전트", "최적화", "강화학습"]
                print(f"  ⚠️  No active AI categories found in DB, using defaults: {valid_categories}")
            else:
                valid_categories = [cat.name for cat in ai_category_objects]
                print(f"  ℹ️  Loaded {len(valid_categories)} valid AI categories from DB: {valid_categories}")

            # Evaluate with LLM(s)
            if self.llm_b:
                # 3-Step Multiturn Debate mode: LLM A → LLM B → LLM A (with conversation context)
                print(f"  💬 3단계 멀티턴 토론 모드 사용")
                result_a_initial, result_b_review, result_a_final = self.evaluate_with_multiturn_debate(
                    application,
                    criteria_list or [],
                    ai_category_objects
                )

                # Merge results
                result = self._merge_debate_results(result_a_initial, result_b_review, result_a_final)
            else:
                # Single LLM mode
                print(f"  🤖 단일 LLM 모드 사용")
                prompt = self.build_evaluation_prompt(application, criteria_list or [], ai_category_objects)
                result_a = self.evaluate_with_single_llm(
                    self.llm_a,
                    prompt,
                    "LLM A",
                    step="[Single LLM Mode]"
                )
                result = result_a

            # Validate evaluation quality
            try:
                self._validate_evaluation_quality(result, criteria_list or [], valid_categories)
            except EvaluationQualityError as e:
                print(f"  ⚠️  Evaluation quality validation failed: {e}")
                print(f"  ℹ️  Continuing with result (validation is advisory)")

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
                # Try weighted scoring first if criteria have weights
                if criteria_list:
                    try:
                        weighted_avg = self.calculate_weighted_score(evaluation_scores, criteria_list)
                        avg_score = weighted_avg
                    except Exception as e:
                        print(f"  ⚠️  Weighted scoring failed, using simple average: {e}")
                        # Fallback to simple average
                        scores = []
                        for criterion in ["innovation", "feasibility", "impact", "clarity"]:
                            if criterion in evaluation_scores and "score" in evaluation_scores[criterion]:
                                scores.append(evaluation_scores[criterion]["score"])
                        avg_score = sum(scores) / len(scores) if scores else 3.0
                else:
                    # Simple average if no criteria list
                    scores = []
                    for criterion in ["innovation", "feasibility", "impact", "clarity"]:
                        if criterion in evaluation_scores and "score" in evaluation_scores[criterion]:
                            scores.append(evaluation_scores[criterion]["score"])
                    avg_score = sum(scores) / len(scores) if scores else 3.0

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

            # Print token usage summary
            token_summary = self.get_token_usage_summary()
            print(f"\n{'='*80}")
            print(f"📊 Token Usage Summary for Application {application.id}")
            print(f"{'='*80}")
            print(f"  LLM A: {token_summary['llm_a']['total_tokens']} tokens "
                  f"({token_summary['llm_a']['api_calls']} calls)")
            if token_summary['llm_b']['api_calls'] > 0:
                print(f"  LLM B: {token_summary['llm_b']['total_tokens']} tokens "
                      f"({token_summary['llm_b']['api_calls']} calls)")
            print(f"  Total: {token_summary['total']['total_tokens']} tokens "
                  f"({token_summary['total']['api_calls']} calls)")
            print(f"{'='*80}\n")

            db.commit()
            return True

        except Exception as e:
            print(f"  ⚠️  평가 중 내부 오류: {e}")
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
