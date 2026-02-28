# TalentAI — Backend

Python FastAPI backend for the TalentAI interview preparation platform.

## Tech Stack

| Library | Purpose |
|---|---|
| FastAPI | REST API framework |
| spaCy | NLP skill extraction |
| scikit-learn | TF-IDF cosine similarity scoring |
| asyncpg | PostgreSQL async driver |
| passlib + bcrypt | Password hashing |
| python-jose | JWT authentication |
| httpx | Async HTTP client |

## Scoring Algorithm

```
Final Score = AI Score × 70% + NLP Similarity × 30%

NLP Similarity = TF-IDF Cosine × 70% + Jaccard Index × 30%
```

## Local Development

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env with your Supabase URL, API key, and secret key

# 4. Run the server
uvicorn main:app --reload --port 8000
```

- API: http://localhost:8000
- Auto docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | /auth/register | Create account |
| POST | /auth/login | Sign in, get JWT |
| GET | /auth/me | Get current user |
| PATCH | /auth/onboard | Complete onboarding |
| POST | /resume/analyze | NLP + AI resume analysis |
| GET | /resume/ | Get saved resume data |
| POST | /resume/jd-match | Compare resume to job posting |
| POST | /resume/cover-letter | Generate cover letter |
| POST | /interview/evaluate | Score interview answer |
| POST | /interview/coach | AI career coach message |
| POST | /interview/gaps | Skill gap learning plan |
| POST | /sessions/ | Save interview session |
| GET | /sessions/ | Get all sessions |
| GET | /sessions/{id} | Get session detail |
| GET | /analytics/ | Get analytics data |
| PATCH | /settings/ | Update user settings |

## Deployment

Deployed to **Render** (free tier).

See `DEPLOYMENT.md` for full step-by-step instructions.
