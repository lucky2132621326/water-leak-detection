"""Azure OpenAI Summary Client

Turns raw detector evidence into human-readable work-order/evidence text.
Never allowed to block or crash the detection response path: any failure
(missing credentials, network error, timeout) falls back to a deterministic
template built from the same evidence data.
"""
import os
from backend.utils.logger import logger

_client = None
_client_init_attempted = False


def _get_client():
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    _client_init_attempted = True

    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not api_key or not endpoint:
        logger.info("[LLM] AZURE_OPENAI_API_KEY/ENDPOINT not set — using template summaries only")
        return None

    try:
        from openai import AzureOpenAI
        _client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )
    except Exception as e:
        logger.warning(f"[LLM] Failed to initialize Azure OpenAI client, falling back to templates: {e}")
        _client = None
    return _client


def build_template_summary(evidence: dict) -> str:
    zone = evidence.get("zone", "UNKNOWN")
    likelihood = evidence.get("likelihood_score", 0)
    residual = evidence.get("residual_lpm", 0.0)
    active_methods = ", ".join(evidence.get("active_methods", [])) or "none"
    # Acoustic corroboration, as a ratio to this rig's own quiet baseline. There
    # is no pressure channel: this rig has no transducer, and the old code
    # printed an *estimated* pressure here as though it were an observation.
    ratio = evidence.get("acoustic_ratio")
    acoustic_note = (f", with pipe noise at {ratio:.2f}x the quiet baseline in the "
                     f"50-150 Hz leak band" if ratio is not None else "")

    return (
        f"Suspected leak in {zone} — likelihood {likelihood}%. "
        f"Flow residual {residual:+.2f} L/min sustained above baseline{acoustic_note}. "
        f"Confirmed by: {active_methods}. Field verification required before dispatch; "
        f"this is an indicative alert, not a confirmed diagnosis."
    )


def generate_work_order_summary(evidence: dict) -> dict:
    """Returns {"summary": str, "source": "llm"|"template"}."""
    client = _get_client()
    if client is None:
        return {"summary": build_template_summary(evidence), "source": "template"}

    prompt = (
        "You write concise field work-order summaries for a water utility crew. "
        "Given leak-detection evidence, write 2-3 sentences: what was detected, "
        "where, how confident, and what evidence supports it. "
        "Never issue valve/pump control instructions — dispatch/field crews handle physical actions. "
        "Always note results are indicative and require field verification.\n\n"
        f"Evidence: {evidence}"
    )
    try:
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            timeout=8,
        )
        text = response.choices[0].message.content.strip()
        if not text:
            raise ValueError("empty LLM response")
        return {"summary": text, "source": "llm"}
    except Exception as e:
        logger.warning(f"[LLM] Azure OpenAI call failed, falling back to template: {e}")
        return {"summary": build_template_summary(evidence), "source": "template"}
