# TalentAI — Full Stack Deployment Guide

## Architecture

```
React Frontend (Vercel)  →  Python FastAPI Backend (Render)  →  PostgreSQL (Supabase)
```

---

## Step 1 — Set Up Supabase Database (5 min)

1. Go to **https://supabase.com** → Sign up free
2. Click **New Project** → name it `talentai` → choose a region → set a DB password
3. Wait ~2 minutes for setup
4. Go to **Settings → Database → Connection String → URI**
5. Copy the connection string — it looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[REF].supabase.co:5432/postgres
   ```
6. **Save this** — you'll need it in Step 2

> The database tables are created automatically when the backend starts for the first time.

---

## Step 2 — Deploy Python Backend to Render (10 min)

1. Push the `talentai-backend/` folder to a GitHub repo
   ```bash
   cd talentai-backend
   git init
   git add .
   git commit -m "TalentAI backend"
   git remote add origin https://github.com/YOUR_USERNAME/talentai-backend.git
   git push -u origin main
   ```

2. Go to **https://render.com** → Sign up with GitHub

3. Click **New → Web Service** → Connect your `talentai-backend` repo

4. Configure:
   | Setting | Value |
   |---|---|
   | Language | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

5. Under **Environment Variables**, add:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | Your Supabase URI from Step 1 |
   | `AI_API_KEY` | Your Anthropic API key |
   | `SECRET_KEY` | Any random string (e.g. `my-super-secret-key-2024`) |

6. Click **Deploy** — wait ~3 minutes

7. Your backend URL will be something like:
   ```
   https://talentai-api.onrender.com
   ```
   Test it: open `https://talentai-api.onrender.com/health` in browser — should return `{"status":"ok"}`

---

## Step 3 — Deploy React Frontend to Vercel (5 min)

1. Copy `api.js` into your React project's `src/` folder

2. Push your React app to GitHub

3. Go to **https://vercel.com** → Sign up with GitHub

4. Click **Add New Project** → import your React repo

5. Under **Environment Variables**, add:
   | Key | Value |
   |---|---|
   | `REACT_APP_API_URL` | `https://talentai-api.onrender.com` |

6. Click **Deploy**

7. Your app is live at:
   ```
   https://talentai.vercel.app
   ```

---

## Local Development

### Backend
```bash
cd talentai-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your Supabase URL, API key, secret key

# Run the server
uvicorn main:app --reload --port 8000
```

Backend runs at: http://localhost:8000
API docs at: http://localhost:8000/docs

### Frontend
```bash
cd talentai-frontend

# Add .env.local file
echo "REACT_APP_API_URL=http://localhost:8000" > .env.local

# Install and run
npm install
npm start
```

---

## What Gets Stored in the Database

| Table | Stores |
|---|---|
| `users` | Name, email, hashed password, plan, streak, daily goal |
| `resumes` | Raw text, extracted skills, ATS score, AI analysis |
| `sessions` | Interview sessions with role, avg score, date |
| `session_questions` | Per-question: answer, score, feedback, ideal answer |
| `skill_gaps` | Gap analyses with coverage % and learning plans |

---

## Free Plan Limits

| Service | Free Limit | Notes |
|---|---|---|
| Supabase | 500MB, 50K rows | More than enough |
| Render | 750 hrs/month | Sleeps after 15min idle — first request wakes it in ~30s |
| Vercel | Unlimited | No limits on free plan |

> **Tip for demos:** Open your Render URL directly 30 seconds before your presentation to wake the server.

---

## Python Libraries Used (for your report)

| Library | Purpose | Aligns with Proposal |
|---|---|---|
| `spaCy` | NLP skill extraction, named entity recognition | ✅ spaCy |
| `scikit-learn` | TF-IDF vectorization, cosine similarity scoring | ✅ scikit-learn |
| `FastAPI` | REST API framework | ✅ Python backend |
| `asyncpg` | Async PostgreSQL connection | ✅ Database |
| `passlib` | bcrypt password hashing | ✅ Security |
| `python-jose` | JWT token authentication | ✅ Auth |
| `httpx` | Async HTTP client for AI API calls | ✅ |

---

## Scoring Algorithm (for your report)

```
Final Score = AI Evaluation (70%) + NLP Similarity (30%)

NLP Similarity = TF-IDF Cosine Similarity (70%) + Jaccard Index (30%)

Where:
  TF-IDF Cosine = sklearn.TfidfVectorizer + cosine_similarity
  Jaccard Index = |A ∩ B| / |A ∪ B| on cleaned token sets
```

This hybrid approach combines:
- **ML-based semantic similarity** (TF-IDF captures word importance)
- **Set-based overlap** (Jaccard as lightweight fallback)
- **AI qualitative judgment** (nuanced feedback on technical correctness)
