"""
LLM Configuration Checker
LLM 설정 확인 스크립트
"""
from app.config import settings

print("="*60)
print("LLM Configuration Check")
print("="*60)
print()

print("[LLM A - Primary]")
print(f"  Base URL: {settings.llm_api_base_url}")
print(f"  API Key: {'*' * 20 if settings.llm_api_key else 'Not Set'}")
print(f"  Model: {settings.llm_model_name}")
print()

print("[LLM B - Secondary for Debate Mode]")
if settings.llm_b_api_base_url:
    print(f"  Base URL: {settings.llm_b_api_base_url}")
    print(f"  API Key: {'*' * 20 if settings.llm_b_api_key else 'Not Set'}")
    print(f"  Model: {settings.llm_b_model_name or settings.llm_model_name}")
    print()
    print("[OK] Debate Mode: ENABLED")
    print("      3-Step Process: LLM A -> LLM B -> LLM A")
else:
    print("  Base URL: Not Set")
    print("  API Key: Not Set")
    print("  Model: Not Set")
    print()
    print("[INFO] Debate Mode: DISABLED")
    print("       Using Single LLM Mode (LLM A only)")
    print()
    print("To enable Debate Mode:")
    print("1. Add these settings to .env file:")
    print("   LLM_B_API_BASE_URL=https://your-llm-b-api.com/v1")
    print("   LLM_B_API_KEY=your_key")
    print("   LLM_B_CREDENTIAL_KEY=your_credential")
    print("   LLM_B_MODEL_NAME=gpt-oss-v2")
    print("2. Restart the server")

print()
print("="*60)
