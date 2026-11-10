"""AI drafting for the Teacher's View comment.

Provider is auto-detected from the configured key:
- Anthropic (Claude): ANTHROPIC_API_KEY env or data/anthropic_key.txt
- OpenAI: OPENAI_API_KEY env or data/openai_key.txt

Per the assessment spec: concrete, warm, parent-friendly English;
distinguish independent vs guided work; never invent what was not
observed; the teacher reviews and edits before saving.
"""

import os

from ..db import DATA_DIR

ANTHROPIC_KEY_FILE = os.path.join(DATA_DIR, "anthropic_key.txt")
OPENAI_KEY_FILE = os.path.join(DATA_DIR, "openai_key.txt")

ANTHROPIC_MODEL = "claude-opus-5-5"
OPENAI_MODEL = os.environ.get("MI_OPENAI_MODEL", "gpt-4o")

SYSTEM_PROMPT = (
    "You are an experienced early-childhood assessor at Think Academy Silicon Valley "
    "writing the Teacher's View section of a TK/K school-readiness assessment report "
    "that parents will read.\n"
    "Rules:\n"
    "- Write in English, 120-180 words, 2-3 short paragraphs, warm and concrete.\n"
    "- Use only the facts provided. Never invent behavior, quotes or results that are "
    "not in the facts. If something was marked Not observed, do not describe it and do "
    "not treat it as a failure.\n"
    "- Clearly distinguish what the child did independently from what they did after "
    "guidance, and frame guidance positively (how the child responded to support).\n"
    "- Mention one or two specific moments (actual answers or actions) when available.\n"
    "- End with one practical, encouraging next step for home practice.\n"
    "- No scores or point totals in the text; no headings; no bullet lists; plain prose."
)


def _read_key(env_name, file_path):
    key = os.environ.get(env_name, "").strip()
    if key:
        return key
    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    return None


def _provider():
    """Returns (provider, key) or (None, None)."""
    key = _read_key("ANTHROPIC_API_KEY", ANTHROPIC_KEY_FILE)
    if key:
        return "anthropic", key
    key = _read_key("OPENAI_API_KEY", OPENAI_KEY_FILE)
    if key:
        return "openai", key
    return None, None


def is_configured():
    return _provider()[0] is not None


def _user_content(facts, existing_draft):
    content = "Observed facts for this child:\n\n" + facts
    if existing_draft.strip():
        content += (
            "\n\nThe teacher has already written this draft. Keep its substance and "
            "any personal observations, improve clarity, warmth and flow:\n\n"
            + existing_draft.strip()
        )
    return content


def _draft_anthropic(key, facts, existing_draft):
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_content(facts, existing_draft)}],
        )
    except anthropic.AuthenticationError:
        return False, "auth_error"
    except anthropic.RateLimitError:
        return False, "rate_limited"
    except anthropic.APIStatusError as e:
        return False, f"api_error_{e.status_code}"
    except anthropic.APIConnectionError:
        return False, "network_error"
    if response.stop_reason == "refusal":
        return False, "refused"
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return (True, text) if text else (False, "empty")


def _draft_openai(key, facts, existing_draft):
    import openai

    client = openai.OpenAI(api_key=key)
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_content(facts, existing_draft)},
            ],
        )
    except openai.AuthenticationError:
        return False, "auth_error"
    except openai.RateLimitError as e:
        # OpenAI reports missing billing / exhausted quota as a 429 too
        msg = str(e)
        if "quota" in msg or "billing" in msg:
            return False, "billing_error"
        return False, "rate_limited"
    except openai.APIStatusError as e:
        return False, f"api_error_{e.status_code}"
    except openai.APIConnectionError:
        return False, "network_error"
    text = (response.choices[0].message.content or "").strip()
    return (True, text) if text else (False, "empty")


def draft_teacher_view(facts: str, existing_draft: str = ""):
    """Returns (ok, text_or_error_code)."""
    provider, key = _provider()
    if provider is None:
        return False, "not_configured"
    if provider == "anthropic":
        return _draft_anthropic(key, facts, existing_draft)
    return _draft_openai(key, facts, existing_draft)
