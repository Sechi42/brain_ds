"""Multilanguage stopword sets for deterministic tokenization.

The scoring tokenizer strips stopwords before computing lexical overlap. The
original implementation only knew English stopwords, so Spanish content
produced edges justified by "shared tokens: de, la, y" — pure noise. These
sets cover the languages brain_ds graphs are written in today; tokens are
filtered against the union so mixed-language cards stay clean without a
per-node language detection pass.

`detect_language` is still exposed for callers that want to know which
language dominates a token set (gap reports, diagnostics).
"""

from __future__ import annotations

STOPWORDS_EN: frozenset[str] = frozenset(
    {
        "a", "an", "and", "or", "the", "for", "to", "of", "in", "on", "by",
        "with", "is", "are", "was", "were", "be", "as", "at", "it", "its",
        "this", "that", "these", "those", "from", "not", "no", "yes", "but",
        "if", "so", "we", "they", "you", "he", "she",
    }
)

STOPWORDS_ES: frozenset[str] = frozenset(
    {
        "de", "la", "el", "en", "y", "a", "que", "los", "las", "por", "para",
        "con", "un", "una", "se", "su", "del", "al", "lo", "le", "es", "son",
        "no", "si", "o", "u", "e", "ni", "tambien", "pero", "como", "mas",
        "muy", "ya", "solo", "todo", "todos", "cada", "sin", "sobre", "hasta",
        "entre", "cuando", "donde", "porque", "esta", "este", "esto", "esa",
        "ese", "eso", "fue", "ser", "hay", "tiene", "tienen", "sus", "les",
    }
)

STOPWORDS_PT: frozenset[str] = frozenset(
    {
        "de", "da", "do", "das", "dos", "a", "o", "as", "os", "em", "e", "ou",
        "que", "para", "por", "com", "um", "uma", "se", "sua", "seu", "ao",
        "na", "no", "nas", "nos", "nao", "sim", "mas", "como", "mais", "ja",
        "todo", "todos", "cada", "sem", "sobre", "ate", "entre", "quando",
    }
)

STOPWORDS_FR: frozenset[str] = frozenset(
    {
        "de", "la", "le", "les", "des", "du", "en", "et", "ou", "que", "qui",
        "pour", "par", "avec", "un", "une", "se", "sa", "son", "ses", "au",
        "aux", "ce", "cette", "ces", "est", "sont", "ne", "pas", "mais",
        "comme", "plus", "tout", "tous", "chaque", "sans", "sur", "entre",
    }
)

STOPWORDS_DE: frozenset[str] = frozenset(
    {
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen",
        "einem", "einer", "und", "oder", "in", "im", "an", "am", "auf", "mit",
        "von", "vom", "zu", "zum", "zur", "fur", "ist", "sind", "war", "nicht",
        "aber", "wie", "mehr", "alle", "jede", "ohne", "uber", "bis", "zwischen",
    }
)

STOPWORDS_IT: frozenset[str] = frozenset(
    {
        "di", "la", "il", "le", "lo", "gli", "i", "in", "e", "o", "che", "chi",
        "per", "da", "con", "un", "una", "uno", "si", "sua", "suo", "sue",
        "al", "alla", "dei", "delle", "del", "della", "non", "ma", "come",
        "piu", "tutto", "tutti", "ogni", "senza", "su", "fra", "tra", "quando",
    }
)

STOPWORDS_BY_LANGUAGE: dict[str, frozenset[str]] = {
    "en": STOPWORDS_EN,
    "es": STOPWORDS_ES,
    "pt": STOPWORDS_PT,
    "fr": STOPWORDS_FR,
    "de": STOPWORDS_DE,
    "it": STOPWORDS_IT,
}

# Union used by the tokenizer: deterministic, no detection pass needed.
ALL_STOPWORDS: frozenset[str] = frozenset().union(*STOPWORDS_BY_LANGUAGE.values())


def detect_language(tokens: set[str] | list[str]) -> str:
    """Return the language whose stopword set matches the most tokens.

    Falls back to "en" on ties or when nothing matches, mirroring the old
    English-only behavior for callers that branch on language.
    """
    token_set = set(tokens)
    if not token_set:
        return "en"
    best_lang = "en"
    best_hits = -1
    for lang, words in STOPWORDS_BY_LANGUAGE.items():
        hits = len(token_set & words)
        if hits > best_hits or (hits == best_hits and lang == "en"):
            best_lang = lang
            best_hits = hits
    return best_lang
