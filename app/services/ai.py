"""AI drafting for the Teacher's View comment (English draft + Chinese version).

Provider is auto-detected from the configured key:
- Anthropic (Claude): ANTHROPIC_API_KEY env or data/anthropic_key.txt
- OpenAI: OPENAI_API_KEY env or data/openai_key.txt

Per the assessment spec: concrete, warm, parent-friendly English;
distinguish independent vs guided work; never invent what was not
observed; the teacher reviews and edits before saving.
"""

import os
import re

from ..db import DATA_DIR

ANTHROPIC_KEY_FILE = os.path.join(DATA_DIR, "anthropic_key.txt")
OPENAI_KEY_FILE = os.path.join(DATA_DIR, "openai_key.txt")

ANTHROPIC_MODEL = "claude-opus-5-5"
OPENAI_MODEL = os.environ.get("MI_OPENAI_MODEL", "gpt-4o")

SYSTEM_PROMPT = (
    "You are an experienced early-childhood assessor at Think Academy Silicon Valley "
    "writing the Teacher's View section of a TK/K school-readiness assessment report "
    "that parents will read.\n"
    "\n"
    "Accuracy rules — these come first:\n"
    "- Use only the facts provided. Every statement must trace back to a specific fact "
    "line. Never invent behavior, quotes, feelings, motives or results.\n"
    "- Each rating states its level, e.g. 'Moderately Engaged (middle of 3)'. Describe it "
    "at exactly that level and never contradict it: a top rating may be called a "
    "strength; a middle rating means 'some of the time' or 'still developing' — never "
    "'strong', 'active' or 'confident'; a lowest rating is an area to grow.\n"
    "- Do not describe HOW the child did something (confidently, quickly, easily, "
    "thoughtfully, eagerly, enthusiastically, smoothly, without hesitation) and do not "
    "assign personality traits (observant, thoughtful nature, resilient) unless a teacher "
    "note or a top rating says exactly that.\n"
    "- Refer to a task by its ability (e.g. Number Sense, Letter Sounds) or its exact "
    "title. Do not guess what a task involved from its title.\n"
    "- Quote words only if they appear in quotation marks in a teacher note.\n"
    "- 'Independent correct' means the child did it on their own; 'correct after "
    "guidance' means they did it with help. Say which, and frame help positively (how the "
    "child responded to support) without claiming improvement or fast learning that was "
    "not recorded.\n"
    "- 'Not observed' is not a failure: leave it out. 'Not yet established' may be "
    "mentioned gently as something to keep practicing.\n"
    "\n"
    "Style:\n"
    "- English, 2-3 short paragraphs, 120-170 words in total (hard limit). Warm, concrete, "
    "plain prose: no headings, no bullet lists, no scores or point totals.\n"
    "- The records do not say whether the child is a boy or a girl. Refer to the child "
    "only by first name: never use he, she, him, her, his, hers, himself, herself (and "
    "not 'they' for the child either). Use the name or its possessive (\"Mia's\"), or "
    "rephrase so no pronoun is needed (e.g. 'said goodbye at drop-off' rather than "
    "'separated from her parents'); vary sentence openings so the name does not start "
    "every sentence.\n"
    "- Put ratings into natural, parent-friendly words at the same level instead of "
    "repeating rubric labels (not 'was noted as very nervous' or 'was fair in focus'; "
    "e.g. 'felt quite shy during introductions', 'stayed focused some of the time'). "
    "Never call an area strong if its rating is middle or lowest, even when a related "
    "task went well. Do not use 'fair' or 'fairly' for a rating (it is ambiguous and "
    "mistranslates); say 'some of the time' or 'still developing' instead.\n"
    "- Mention one or two specific moments from teacher notes or story responses when "
    "available.\n"
    "- End with one practical next step for home that follows from a recorded area to "
    "practice."
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


def _zh_system_prompt():
    from ..report_i18n import ABILITY_ZH, STAGE_ZH

    glossary = "; ".join(f"{en} = {zh}" for en, zh in {**STAGE_ZH, **ABILITY_ZH}.items())
    return (
        "You adapt the Teacher's View section of a TK/K school-readiness assessment "
        "report from English into Simplified Chinese for Chinese-speaking parents.\n"
        "Rules:\n"
        "- Write natural, warm, fluent Chinese, as an experienced Chinese kindergarten "
        "teacher would write to parents — not a word-for-word translation.\n"
        "- Faithfulness comes first: carry over every fact exactly as stated, one by one. "
        "Never merge two separate facts into one, never reinterpret what the child did, "
        "and add nothing — no new behavior, praise, quotes, results, or category labels "
        "(such as 在…方面) that the English does not have.\n"
        "- Keep the distinction between what the child did independently and what they "
        "did after guidance.\n"
        "- Refer to the child only by name: never use 他 or 她 (or 他的 / 她的) for the child. "
        "Repeat the name where needed, or leave the subject out where natural Chinese allows. "
        "(他人 / 其他 meaning 'others' are fine.)\n"
        "- Keep the child's name exactly as written in English. Keep words the child said in "
        "English (anything in quotation marks, e.g. 'big/little') in English.\n"
        "- Keep each rating's level exactly: do not make a middle rating sound stronger or "
        "weaker than the English does. 'fair' / 'fairly' describing how well something went "
        "means 一般 / 还可以, never 公平 (unless it is about sharing equally, like sharing "
        "cakes fairly).\n"
        "- Keep the same paragraph structure; no headings, no bullet lists, no scores.\n"
        "- Only when the English itself names one of these activities or abilities, use "
        "the matching report term: " + glossary + ". Do not introduce these terms otherwise.\n"
        "- Output only the Chinese text."
    )


def _user_content(facts, existing_draft):
    content = "Observed facts for this child:\n\n" + facts
    if existing_draft.strip():
        content += (
            "\n\nThe teacher has already written this draft. Keep its substance and "
            "any personal observations, improve clarity, warmth and flow:\n\n"
            + existing_draft.strip()
        )
    return content


def _complete_anthropic(key, system, user):
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
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


def _complete_openai(key, system, user, temperature=None):
    import openai

    client = openai.OpenAI(api_key=key)
    extra = {} if temperature is None else {"temperature": temperature}
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **extra,
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


def _complete(system, user, openai_temperature=None):
    """Returns (ok, text_or_error_code) from whichever provider is configured."""
    provider, key = _provider()
    if provider is None:
        return False, "not_configured"
    if provider == "anthropic":
        return _complete_anthropic(key, system, user)
    return _complete_openai(key, system, user, openai_temperature)


MAX_WORDS = 175  # the prompt asks for <= 170; models overshoot, so enforce it here

SHORTEN_PROMPT = (
    "Shorten this Teacher's View comment for parents to at most 160 words. Keep every "
    "fact, every distinction between independent work and work done with guidance, and "
    "the closing home suggestion. Remove repetition and general statements first. Do not "
    "add anything new. Keep 2-3 short paragraphs of plain prose. Keep referring to the "
    "child by name only (no he/she/his/her/they). Output only the comment."
)


# Records carry no gender, so comments name the child instead of guessing he/she.
# The prompts ask for that; these checks catch the occasional slip.
_GENDERED_EN = re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.I)
_GENDERED_ZH = re.compile(r"(?<!其)他(?![人们])|她(?!们)")  # 他人 / 其他 = "others"

NAME_ONLY_EN = (
    "In this comment about a child, remove every he, she, him, her, his, hers, himself or "
    "herself that refers to the child:\n"
    "- he / she / him / her -> the child's first name (or rephrase if the name was just used)\n"
    "- his / her (possessive) -> the name's possessive, e.g. \"Mia's\"\n"
    "- himself / herself -> NEVER the name; rephrase instead: 'introduced himself' -> "
    "'did the self-introduction', 'on her own' -> 'independently'\n"
    "- common phrases count too: 'separated from her parents' -> 'said goodbye at "
    "drop-off', 'his parents' -> 'the family'\n"
    "Do not use they/them for the child. Keep every other word exactly as it is. "
    "Output only the comment."
)
NAME_ONLY_ZH = (
    "这是一段关于孩子的评语。把所有指代这个孩子的「他」「她」「他的」「她的」改成孩子的名字，"
    "或在中文自然的情况下省略主语。「他人」「其他」等表示别人的词不要改。"
    "其他内容一字不改。只输出改好的评语。"
)


def _name_only(text, pattern, fix_prompt, attempts=2):
    for _ in range(attempts):
        if not pattern.search(text):
            break
        ok, fixed = _complete(fix_prompt, text, openai_temperature=0)
        if not (ok and fixed.strip()):
            break
        text = fixed
    return text


def draft_teacher_view(facts: str, existing_draft: str = ""):
    """English Teacher's View. Returns (ok, text_or_error_code)."""
    # Low temperature: stick to the recorded facts rather than embellish them.
    ok, text = _complete(SYSTEM_PROMPT, _user_content(facts, existing_draft), openai_temperature=0.3)
    if not ok:
        return ok, text
    if len(text.split()) > MAX_WORDS:
        s_ok, short = _complete(SHORTEN_PROMPT, text, openai_temperature=0.2)
        if s_ok and len(short.split()) < len(text.split()):
            text = short
    return True, _name_only(text, _GENDERED_EN, NAME_ONLY_EN)


def translate_teacher_view_zh(text_en: str):
    """Chinese version of an English Teacher's View. Returns (ok, text_or_error_code)."""
    if not text_en.strip():
        return False, "empty_source"
    # Low temperature: the Chinese should track the English closely, not vary.
    ok, zh = _complete(_zh_system_prompt(), text_en.strip(), openai_temperature=0.2)
    if not ok:
        return ok, zh
    return True, _name_only(zh, _GENDERED_ZH, NAME_ONLY_ZH)
