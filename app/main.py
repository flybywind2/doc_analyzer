"""
FastAPI Main Application
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.config import settings
from app.database import init_db
from app.routers import auth, users, departments, categories, applications, evaluations, statistics, pages, scheduled_jobs

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
app.mount("/images", StaticFiles(directory="images"), name="images")

# Jinja2 templates
templates = Jinja2Templates(directory="app/templates")


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Custom exception handler for HTTP exceptions
    Redirects to login page for 401/403 errors on HTML requests
    """
    # Check if this is an HTML request (not an API call)
    accept_header = request.headers.get("accept", "")
    is_html_request = "text/html" in accept_header

    # For 401 Unauthorized or 403 Forbidden on HTML requests, redirect to login
    if exc.status_code in [401, 403] and is_html_request:
        return RedirectResponse(url="/", status_code=302)

    # For API requests or other status codes, return JSON response
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers
    )


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
app.include_router(scheduled_jobs.router, prefix="/api")


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

    # Start job scheduler
    from app.services.scheduler import job_scheduler
    job_scheduler.start()
    print("⏰ Job scheduler started")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event"""
    # Stop job scheduler
    from app.services.scheduler import job_scheduler
    job_scheduler.shutdown()
    print("⏰ Job scheduler stopped")


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
