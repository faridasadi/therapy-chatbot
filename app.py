from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from db import Base, engine, get_db_session
import analytics

# Initialize FastAPI app
app = FastAPI(title="Therapyyy Bot API")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    # Create database tables
    Base.metadata.create_all(bind=engine)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the analytics dashboard."""
    context = {
        "request": request,  # Required by Jinja2Templates
        "metrics": analytics.get_subscription_metrics(),
        "user_growth": analytics.get_user_growth_data(),
        "message_activity": analytics.get_message_activity_data(),
        "theme_distribution": analytics.get_theme_distribution(),
        "sentiment_data": analytics.get_sentiment_over_time()
    }
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/")
async def index():
    return {"status": "healthy", "message": "Therapyyy Bot Server is running"}