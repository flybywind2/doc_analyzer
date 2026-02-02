"""
FastAPI Main Application
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import auth, users, departments, categories, applications, evaluations, statistics, pages

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
# Web page routers (no prefix)
app.include_router(pages.router)

# Auth router (special - no /api prefix for compatibility)
app.include_router(auth.router)

# API routers (with /api prefix)
app.include_router(users.router, prefix="/api")
app.include_router(departments.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(evaluations.router, prefix="/api")
app.include_router(statistics.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """Startup event"""
    print(f"🚀 {settings.app_name} v{settings.app_version} started")
    
    # Initialize default data
    from app.database import SessionLocal
    from app.models.init_data import init_default_data
    from app.models.generate_dummy_data import generate_dummy_data
    
    db = SessionLocal()
    try:
        init_default_data(db)
        # Generate dummy data for testing
        generate_dummy_data(db)
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint - redirect to dashboard"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.app_version}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=settings.debug)
