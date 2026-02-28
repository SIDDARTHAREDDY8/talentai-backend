"""
TalentAI — FastAPI Backend
Python + spaCy NLP + scikit-learn similarity scoring
"""

from dotenv import load_dotenv
load_dotenv()  # Must be first — loads .env before anything else reads os.getenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import create_tables
from routes import auth, resume, interview, sessions, analytics, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="TalentAI API",
    description="AI-powered interview preparation platform backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://talentai-frontend.vercel.app",
        "https://*.vercel.app",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/auth",      tags=["Authentication"])
app.include_router(resume.router,    prefix="/resume",    tags=["Resume"])
app.include_router(interview.router, prefix="/interview", tags=["Interview"])
app.include_router(sessions.router,  prefix="/sessions",  tags=["Sessions"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(settings.router,  prefix="/settings",  tags=["Settings"])


@app.get("/")
async def root():
    return {"status": "TalentAI API running", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "ok"}
