"""
AI Client — Anthropic API calls (server-side key only).
All user-facing apiKey fields have been removed.
"""

import os
import json
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

API_KEY = os.getenv("AI_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"
BASE_URL = "https://api.anthropic.com/v1/messages"


async def _call(prompt: str, system: str = "You are an expert AI assistant.", max_tokens: int = 1000) -> str:
    if not API_KEY:
        logger.warning("AI_API_KEY not set — skipping AI call")
        return ""

    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
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
            if resp.status_code != 200:
                logger.error(f"AI API error {resp.status_code}: {resp.text[:200]}")
                return ""
            return resp.json().get("content", [{}])[0].get("text", "")
        except Exception as e:
            logger.exception(f"AI API exception: {e}")
            return ""


async def _call_json(prompt: str, system: str = "Return only valid JSON, no markdown fences.", max_tokens: int = 800) -> Optional[dict]:
    text = await _call(prompt, system, max_tokens)
    if not text:
        return None
    try:
        clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.error(f"JSON parse failed, raw: {text[:200]}")
        return None


async def ai_evaluate_answer(question: str, user_answer: str, reference: str) -> Optional[dict]:
    return await _call_json(
        f"""Senior technical interviewer. Evaluate strictly.
Question: {question}
Candidate answer: {user_answer}
Reference answer: {reference}

Return JSON: {{
  "score": 0-100,
  "feedback": "2-3 specific sentences on what was good and what was missing",
  "ideal": "model answer in 3-5 sentences",
  "missed": "the single most important concept missed, or empty string"
}}"""
    )


async def ai_analyze_resume(resume_text: str) -> Optional[dict]:
    return await _call_json(
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
}}"""
    )


async def ai_match_jd(resume_text: str, jd_text: str) -> Optional[dict]:
    return await _call_json(
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
}}"""
    )


async def ai_generate_cover_letter(resume_text: str, jd_text: str, company: str, tone: str) -> str:
    from datetime import date
    today = date.today().strftime("%B %d, %Y")
    letter = await _call(
        f"""Write a professional cover letter body.
Resume: {resume_text[:2000]}
Job Description: {jd_text[:1500]}
Company: {company or "the company"}
Tone: {tone}

Structure exactly:
Dear Hiring Manager,

[Opening paragraph - strong hook]

[Middle paragraph - skills aligned with JD]

[Closing paragraph - call to action]

Sincerely,
[Candidate Full Name from resume]

~300 words. Sound human and specific. No clichés. Start directly with Dear Hiring Manager.""",
        system="You are an expert cover letter writer.",
        max_tokens=1000,
    )
    return f"{today}\n\n{letter.strip()}"


async def ai_learning_plan(role: str, missing_skills: list) -> Optional[dict]:
    return await _call_json(
        f"""Create a learning plan for someone targeting {role}.
Missing skills: {', '.join(missing_skills[:10])}

Return JSON: {{
  "priority": ["top 3 skills to learn first with reason"],
  "timeline": "X weeks",
  "resources": {{"skill_name": "specific resource or course"}},
  "weeklyPlan": ["week 1 focus", "week 2 focus", "week 3 focus"]
}}"""
    )


async def ai_coach_reply(messages: list, skills: list, level: str, target_role: str) -> str:
    system = f"""You are an expert AI career coach for tech professionals.
User profile: Skills: {', '.join(skills[:20]) or 'not provided'}. Level: {level or 'unknown'}. Target role: {target_role or 'not specified'}.
Be practical, specific, and encouraging. Keep responses under 200 words unless depth is genuinely needed."""

    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 600,
        "system": system,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(BASE_URL, headers=headers, json=body)
            if resp.status_code != 200:
                return "Sorry, I couldn't respond right now. Please try again."
            return resp.json().get("content", [{}])[0].get("text", "Sorry, I couldn't respond.")
        except Exception:
            return "Sorry, I couldn't respond right now."
