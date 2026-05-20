"""
TalentAI — FastAPI Backend
"""

from dotenv import load_dotenv
load_dotenv()

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import create_tables
from routes import auth, resume, interview, sessions, analytics, settings, billing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

limiter = Limiter(key_func=get_remote_address)

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="TalentAI API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(auth.router,      prefix="/auth",      tags=["Authentication"])
app.include_router(resume.router,    prefix="/resume",    tags=["Resume"])
app.include_router(interview.router, prefix="/interview", tags=["Interview"])
app.include_router(sessions.router,  prefix="/sessions",  tags=["Sessions"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(settings.router,  prefix="/settings",  tags=["Settings"])
app.include_router(billing.router,   prefix="/billing",   tags=["Billing"])

# Expose limiter for use in route files
app.state.limiter = limiter


@app.get("/")
async def root():
    return {"status": "TalentAI API running", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
