"""Language utilities used across the agent, ensemble, and RAG chain.

The dropdown in the UI sends ISO-639-1 codes (e.g., "en", "ur", "ar"). We
translate those into a system-prompt directive that forces the LLM to
respond in that language and translate any English tool/document outputs.

IMPORTANT: the directive is emitted for EVERY language including English.
Earlier this returned "" for English on the assumption no instruction was
needed — but that broke mid-conversation switches: after the assistant had
been replying in (say) Japanese, switching the UI to English sent NO directive,
so the model followed the Japanese conversation history and kept answering in
Japanese. Emitting an explicit English directive (and telling the model the
current-turn language overrides earlier turns) fixes that.
"""

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ur": "Urdu",
    "ar": "Arabic",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "tr": "Turkish",
    "nl": "Dutch",
    "pl": "Polish",
    "sv": "Swedish",
    "id": "Indonesian",
    "th": "Thai",
    "vi": "Vietnamese",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "ml": "Malayalam",
    "gu": "Gujarati",
    "kn": "Kannada",
    "fa": "Persian",
    "he": "Hebrew",
    "el": "Greek",
    "cs": "Czech",
    "ro": "Romanian",
    "hu": "Hungarian",
    "uk": "Ukrainian",
    "fil": "Filipino",
    "ms": "Malay",
    "sw": "Swahili",
}


def language_directive(language: str | None) -> str:
    """Return a system-prompt suffix that forces the response language.

    Emitted for every known language, INCLUDING English, so that switching
    languages mid-conversation actually takes effect: the directive explicitly
    overrides the language used in earlier turns. Unknown/missing codes fall
    back to English.
    """
    code = (language or "en").lower()
    name = LANGUAGE_NAMES.get(code, "English")

    if name == "English":
        # Explicit English directive — NOT empty — so a switch back to English
        # mid-conversation overrides any earlier non-English turns.
        return (
            "\n\nIMPORTANT: Respond entirely in English, using natural English "
            "phrasing. This applies even if earlier messages in this "
            "conversation were in another language — the user has selected "
            "English for this turn, so reply in English regardless of the "
            "language used previously."
        )

    return (
        f"\n\nIMPORTANT: You MUST respond entirely in {name}. This applies even "
        f"if earlier messages in this conversation were in a different language "
        f"— the user has selected {name} for this turn, so reply in {name} "
        f"regardless of the language used previously. "
        f"Translate any English tool outputs (weather, web search results, "
        f"document snippets, calculator results, etc.) into {name} before "
        f"presenting them to the user. Use proper {name} script and natural "
        f"phrasing. Do not mix English with {name} unless the user explicitly "
        f"asks for it. Code, identifiers, and proper nouns may stay in their "
        f"original form."
    )
