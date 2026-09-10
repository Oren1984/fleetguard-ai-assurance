"""Small local RAG over the SOP markdown documents.

Retrieval uses TF-IDF + cosine similarity (scikit-learn) rather than a
hosted embeddings API - this keeps the RAG path fully functional in mock
mode with zero external dependencies, and deterministic for testing.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings
from app.exceptions import SopNotFoundError

_SECTION_SPLIT_RE = re.compile(r"(?=^## )", re.MULTILINE)


@dataclass
class SopChunk:
    doc: str
    section: str
    text: str


@dataclass
class SopMatch:
    doc: str
    section: str
    similarity: float
    excerpt: str


class SopIndex:
    def __init__(self, docs_dir: Optional[str] = None):
        self.docs_dir = Path(docs_dir or settings.SOP_DOCS_DIR)
        self.chunks: list[SopChunk] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._matrix = None
        self._load()

    def _load(self) -> None:
        if not self.docs_dir.exists():
            raise SopNotFoundError(f"SOP documents directory not found: {self.docs_dir}")

        files = sorted(self.docs_dir.glob("*.md"))
        if not files:
            raise SopNotFoundError(f"No SOP documents found in {self.docs_dir}")

        for path in files:
            text = path.read_text(encoding="utf-8")
            sections = _SECTION_SPLIT_RE.split(text)
            for section in sections:
                section = section.strip()
                if not section:
                    continue
                title_line = section.splitlines()[0].lstrip("# ").strip()
                self.chunks.append(SopChunk(doc=path.name, section=title_line or path.stem, text=section))

        if not self.chunks:
            raise SopNotFoundError(f"SOP documents in {self.docs_dir} contained no usable content")

        corpus = [c.text for c in self.chunks]
        # Bigrams + sublinear TF: several SOP sections share the same unigram
        # vocabulary (temperature/setpoint/extreme heat/route delay) whether
        # they describe when to act or when NOT to act. Phrase-level matching
        # is what actually distinguishes "severe deviation ... divert" from
        # "deviation is under 2C ... continue" - see SopIndex module tests.
        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self._matrix = self._vectorizer.fit_transform(corpus)

    def search(self, query: str, top_k: int = 2) -> list[SopMatch]:
        if not query or not query.strip():
            return []

        query_vec = self._vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self._matrix)[0]
        ranked = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)

        matches: list[SopMatch] = []
        for idx in ranked[:top_k]:
            score = float(similarities[idx])
            if score < settings.SOP_MIN_SIMILARITY:
                continue
            chunk = self.chunks[idx]
            excerpt = chunk.text
            if len(excerpt) > 600:
                excerpt = excerpt[:600].rsplit(" ", 1)[0] + "..."
            matches.append(SopMatch(doc=chunk.doc, section=chunk.section, similarity=round(score, 4), excerpt=excerpt))
        return matches


_index: Optional[SopIndex] = None


def get_index() -> SopIndex:
    global _index
    if _index is None:
        _index = SopIndex()
    return _index


def reset_index() -> None:
    """Used by tests to force re-loading the index (e.g. with a different docs_dir)."""
    global _index
    _index = None


RISK_LEVEL_QUERY_HINTS = {
    "HIGH": "severe deviation active refrigeration failure high risk divert approved facility human approval",
    "MEDIUM": "moderate deviation change route reduce transit time",
    "LOW": "minor deviation continue journey no action required within setpoint",
}

# Short, retrieval-oriented phrasing per risk factor. Deliberately NOT the
# same text as the human-readable `detail` string on each reason: the
# detail sentences are full of numbers and connective words that dilute
# TF-IDF matching and can even pull in a negated SOP section (e.g. the
# "continue journey" conditions list uses the same vocabulary - temperature,
# setpoint, extreme heat, route delay - as the reasons that require action).
FACTOR_QUERY_HINTS = {
    "temperature_deviation": "temperature deviation above setpoint",
    "temperature_trend": "sustained rising temperature trend refrigeration failure",
    "extreme_weather": "extreme external heat weather refrigeration unit strain",
    "route_delay": "route delay extends transit time cold chain impact",
    "weather_data_unavailable": "weather data unavailable reduced confidence",
    "nominal": "cargo temperature within setpoint no risk factors",
}


def build_query(evidence_snapshot: dict, reasons: list[dict], risk_level: str = "") -> str:
    """Turn structured risk evidence into a short, keyword-dense retrieval
    query. Including a risk-level hint matters: several SOP sections share
    the same vocabulary (temperature, setpoint, extreme heat, route delay)
    whether they describe when to act or when NOT to act, so a bare keyword
    query can retrieve the wrong (negated) section. Anchoring the query with
    the actual classification biases retrieval toward the matching procedure.
    """
    parts = [RISK_LEVEL_QUERY_HINTS.get(risk_level, "")]
    for r in reasons:
        factor = r.get("factor", "")
        parts.append(FACTOR_QUERY_HINTS.get(factor, factor.replace("_", " ")))
    return " ".join(p for p in parts if p)
