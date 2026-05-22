from pathlib import Path

DOMAIN_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "domain_templates"

SKIP_COMPLEXITY_LEVELS = {"simple", "small"}

TIME_BUDGET_SECONDS = {
    "medium": 15,
    "large": 20,
    "enterprise": 25,
}

CONFIDENCE_DISPLAY_THRESHOLD = 0.4
CONFIDENCE_DEFAULT_SHOW = 0.7

DUAL_MODEL_A = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
DUAL_MODEL_B = "THUDM/GLM-Z1-9B-0414"
DUAL_MODEL_FALLBACK = "Qwen/Qwen3-8B"

DEVILS_ADVOCATE_MODEL = "THUDM/GLM-Z1-9B-0414"

MIN_HISTORY_PROJECTS = 50
MIN_HISTORY_WITH_FEATURES = 20
MIN_VECTOR_RESULTS = 5