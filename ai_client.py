"""
AI Client — wraps Anthropic API calls
All LLM-powered features go through here.
"""

import os
import json
import httpx
from typing import Optional

ANTHROPIC_API_KEY = os.getenv("AI_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"
BASE_URL = "https://api.anthropic.com/v1/messages"


async def call_ai(
    prompt: str,
    system: str = "You are an expert AI assistant.",
    max_tokens: int = 1000,
    api_key: Optional[str] = None,
) -> str:
    """Send a prompt to the AI and return the text response."""
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        print("⚠️  No AI API key configured. Set AI_API_KEY in .env")
        return ""

    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(BASE_URL, headers=headers, json=body)
            data = resp.json()
            print(f"🔍 AI API status: {resp.status_code}, key_prefix: {key[:15] if key else 'NONE'}")
            if resp.status_code != 200:
                print(f"❌ AI API error {resp.status_code}: {data}")
                return ""
            text = data.get("content", [{}])[0].get("text", "")
            print(f"✅ AI API responded, {len(text)} chars")
            return text
        except Exception as e:
            print(f"❌ AI API exception: {e}")
            return ""  


async def call_ai_json(
    prompt: str,
    system: str = "Return only valid JSON, no markdown fences.",
    max_tokens: int = 800,
    api_key: Optional[str] = None,
) -> Optional[dict]:
    """Call AI and parse JSON response. Returns None on failure."""
    text = await call_ai(prompt, system, max_tokens, api_key)
    if not text:
        print("⚠️  call_ai returned empty text")
        return None
    try:
        clean = text.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        print(f"✅ AI JSON parsed OK: {list(result.keys())}")
        return result
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e} | Raw text: {text[:200]}")
        return None


# ── Specific AI tasks ─────────────────────────────────────────────────────────

async def ai_evaluate_answer(
    question: str,
    user_answer: str,
    reference: str,
    api_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Ask AI to evaluate a candidate's interview answer.
    Returns {score, feedback, ideal, missed}
    """
    return await call_ai_json(
        f"""Senior technical interviewer. Evaluate strictly.
Question: {question}
Candidate answer: {user_answer}
Reference answer: {reference}

Return JSON: {{
  "score": 0-100,
  "feedback": "2-3 specific sentences on what was good and what was missing",
  "ideal": "model answer in 3-5 sentences",
  "missed": "the single most important concept the candidate missed, or empty string"
}}""",
        api_key=api_key,
    )


async def ai_analyze_resume(resume_text: str, api_key: Optional[str] = None) -> Optional[dict]:
    """
    Ask AI to assess the resume holistically.
    Returns {strengths, level, bestRole, improvements, summary, atsScore, atsIssues}
    """
    return await call_ai_json(
        f"""Analyze this resume as an expert recruiter.
Resume: {resume_text[:3000]}

Return JSON: {{
  "strengths": ["2-3 strengths as full sentences"],
  "level": "Junior|Mid|Senior",
  "bestRole": "Software Engineer|Data Scientist|Data Engineer|ML Engineer|Frontend Developer",
  "improvements": ["2 concrete improvement suggestions"],
  "summary": "2-sentence profile summary",
  "atsScore": 0-100,
  "atsIssues": ["up to 3 ATS/formatting issues found"]
}}""",
        api_key=api_key,
    )


async def ai_match_jd(resume_text: str, jd_text: str, api_key: Optional[str] = None) -> Optional[dict]:
    """Compare resume to job description."""
    return await call_ai_json(
        f"""Hiring manager. Compare resume to job description.
Resume: {resume_text[:2500]}
Job Description: {jd_text[:2000]}

Return JSON: {{
  "matchScore": 0-100,
  "verdict": "Strong Match|Good Match|Partial Match|Weak Match",
  "matchedKeywords": [],
  "missingKeywords": [],
  "strengths": ["2-3 reasons they're a good fit"],
  "gaps": ["2-3 concerns or gaps"],
  "recommendation": "2-sentence hiring recommendation",
  "tailoredTip": "1 specific tip to tailor the application"
}}""",
        api_key=api_key,
    )


async def ai_generate_cover_letter(
    resume_text: str,
    jd_text: str,
    company: str,
    tone: str,
    api_key: Optional[str] = None,
) -> str:
    """Generate a tailored cover letter."""
    return await call_ai(
        f"""Write a complete, professional cover letter.
Resume: {resume_text[:2000]}
Job Description: {jd_text[:1500]}
Company: {company or "the company"}
Tone: {tone}

You MUST follow this exact structure:
[Today's Date]

Dear Hiring Manager,

[Opening paragraph - strong hook, do NOT start with "I am writing to"]

[Middle paragraph - specific alignment between candidate skills and JD requirements]

[Closing paragraph - strong close with call to action]

Sincerely,
[Candidate Full Name from resume]

Requirements:
- ~300 words total
- Sound human and specific, not generic
- No clichés like "team player" or "hardworking"
- Include the date, salutation, 3 paragraphs, and sign-off exactly as shown above

Return only the complete letter text.""",
        system="You are an expert cover letter writer. Always include proper letter formatting with date, salutation, body paragraphs, and sign-off.",
        max_tokens=1000,
        api_key=api_key,
    )


async def ai_learning_plan(role: str, missing_skills: list, api_key: Optional[str] = None) -> Optional[dict]:
    """Generate a personalized learning plan for missing skills."""
    return await call_ai_json(
        f"""Create a learning plan for someone targeting {role}.
Missing skills: {', '.join(missing_skills[:10])}

Return JSON: {{
  "priority": ["top 3 skills to learn first with reason"],
  "timeline": "X weeks",
  "resources": {{"skill_name": "specific resource or course"}},
  "weeklyPlan": ["week 1 focus", "week 2 focus", "week 3 focus"]
}}""",
        api_key=api_key,
    )
