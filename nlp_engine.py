"""
NLP Engine
  - spaCy for resume skill extraction and named entity recognition
  - scikit-learn TF-IDF cosine similarity for answer evaluation
  - Jaccard similarity as a lightweight fallback
"""

import re
from typing import List, Tuple

# scikit-learn for TF-IDF similarity scoring
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️  scikit-learn not available, using Jaccard only")

# spaCy is optional — regex extraction works without it
nlp = None
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
        print("✅ spaCy loaded")
    except OSError:
        print("⚠️  spaCy model not found. Using regex extraction only.")
except Exception as e:
    print(f"⚠️  spaCy not available: {e}. Using regex extraction only.")

# ── Master skill list ─────────────────────────────────────────────────────────
SKILLS = [
    # Languages
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust",
    "Swift", "Kotlin", "R", "Scala", "Bash", "MATLAB",
    # Frontend
    "React", "Vue.js", "Angular", "HTML", "CSS", "Webpack", "Next.js", "Redux",
    "Tailwind", "Sass",
    # Backend
    "Node.js", "FastAPI", "Django", "Flask", "Spring", "Express", "GraphQL",
    "REST APIs", "Microservices", "gRPC",
    # Data / ML
    "Machine Learning", "Deep Learning", "NLP", "TensorFlow", "PyTorch",
    "scikit-learn", "Keras", "Pandas", "NumPy", "Matplotlib", "Seaborn",
    "Tableau", "Power BI", "Data Visualization", "Statistics",
    # Data Engineering
    "SQL", "PostgreSQL", "MongoDB", "Redis", "MySQL", "Apache Spark", "Kafka",
    "Airflow", "ETL", "Data Warehousing", "Hadoop", "Hive", "dbt",
    # DevOps / Cloud
    "Docker", "Kubernetes", "AWS", "GCP", "Azure", "CI/CD", "Jenkins",
    "Terraform", "Linux", "Git",
    # CS Fundamentals
    "Data Structures", "Algorithms", "System Design", "OOP", "Design Patterns",
    # MLOps
    "MLOps", "MLflow", "Model Deployment", "Feature Engineering",
    # Soft skills
    "Agile", "Scrum", "JIRA",
]

# Compile patterns once at import time for speed
_SKILL_PATTERNS = {
    skill: re.compile(
        r"\b" + re.escape(skill).replace(r"\.", r"\.?") + r"\b",
        re.IGNORECASE,
    )
    for skill in SKILLS
}


def extract_skills(text: str) -> List[str]:
    """
    Two-pass skill extraction:
    1. Regex matching against master skill list (fast, high precision)
    2. spaCy NER to catch additional technical terms not in our list
    Returns deduplicated list preserving original casing from master list.
    """
    found = []

    # Pass 1: regex over master list
    for skill, pattern in _SKILL_PATTERNS.items():
        if pattern.search(text):
            found.append(skill)

    # Pass 2: spaCy NER — catch ORG / PRODUCT entities that look like tech
    if nlp:
        doc = nlp(text[:10000])  # limit to first 10k chars for speed
        for ent in doc.ents:
            if ent.label_ in ("ORG", "PRODUCT") and len(ent.text) > 2:
                candidate = ent.text.strip()
                # Only add if it's a plausible tech term not already found
                if candidate not in found and _looks_like_tech(candidate):
                    found.append(candidate)

    return found


def _looks_like_tech(text: str) -> bool:
    """Heuristic: tech terms tend to be short, CamelCase or all-caps."""
    if len(text) > 30:
        return False
    if re.match(r"^[A-Z][a-z]+([A-Z][a-z]+)+$", text):  # CamelCase
        return True
    if re.match(r"^[A-Z]{2,}$", text):                    # Acronym
        return True
    return False


# ── Similarity scoring ────────────────────────────────────────────────────────

def tfidf_similarity(text_a: str, text_b: str) -> float:
    """
    TF-IDF cosine similarity between two texts.
    Returns 0.0 – 1.0.
    Used as the ML-based component of answer scoring.
    """
    if not text_a.strip() or not text_b.strip():
        return 0.0
    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),   # unigrams + bigrams
            max_features=5000,
        )
        tfidf = vectorizer.fit_transform([text_a, text_b])
        score = cosine_similarity(tfidf[0], tfidf[1])[0][0]
        return float(score)
    except Exception:
        return jaccard_similarity(text_a, text_b)


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    Jaccard index on cleaned token sets — fast lightweight fallback.
    Returns 0.0 – 1.0.
    """
    def tokenize(t):
        return set(
            w for w in re.sub(r"[^\w\s]", "", t.lower()).split()
            if len(w) > 3
        )

    A, B = tokenize(text_a), tokenize(text_b)
    if not A or not B:
        return 0.0
    intersection = len(A & B)
    union = len(A | B)
    return intersection / union if union else 0.0


def compute_answer_score(user_answer: str, reference_answer: str) -> Tuple[int, float, float]:
    """
    Blend TF-IDF cosine similarity (70%) + Jaccard (30%).
    Returns (blended_score_0_100, tfidf_raw, jaccard_raw)
    """
    tfidf = tfidf_similarity(user_answer, reference_answer)
    jacc  = jaccard_similarity(user_answer, reference_answer)
    blended = (tfidf * 0.7) + (jacc * 0.3)
    score = max(5, min(100, round(blended * 100)))
    return score, tfidf, jacc


def assess_resume_level(skills: List[str], raw_text: str) -> str:
    """
    Rule-based seniority classification based on keyword signals in resume text.
    """
    text_lower = raw_text.lower()
    senior_signals = ["senior", "lead", "principal", "staff", "architect",
                       "manager", "director", "10+ years", "8+ years", "7+ years"]
    mid_signals    = ["mid", "intermediate", "3+ years", "4+ years", "5+ years", "6+ years"]

    for s in senior_signals:
        if s in text_lower:
            return "Senior"
    for s in mid_signals:
        if s in text_lower:
            return "Mid"
    return "Junior"


def best_role_for_skills(skills: List[str]) -> str:
    """
    Returns the role whose required skill set has the highest overlap
    with the candidate's extracted skills.
    """
    ROLE_SKILLS = {
        "Software Engineer":  ["Python","JavaScript","React","Node.js","SQL","Git","Docker","System Design","Algorithms"],
        "Data Scientist":     ["Python","Machine Learning","Statistics","Pandas","NumPy","scikit-learn","TensorFlow","SQL"],
        "Data Engineer":      ["Python","SQL","Apache Spark","Kafka","Airflow","AWS","ETL","Docker"],
        "ML Engineer":        ["Python","TensorFlow","PyTorch","MLOps","Docker","Kubernetes","scikit-learn"],
        "Frontend Developer": ["JavaScript","TypeScript","React","CSS","HTML","Git","Webpack"],
    }
    skills_lower = {s.lower() for s in skills}
    best, best_score = "Software Engineer", 0
    for role, reqs in ROLE_SKILLS.items():
        overlap = sum(1 for r in reqs if r.lower() in skills_lower)
        if overlap > best_score:
            best, best_score = role, overlap
    return best
