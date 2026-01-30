"""Main FastAPI application."""
import uuid
import time
from contextvars import ContextVar
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from routes import upload, search, status, diagnostics, internal
import logging
import traceback

# Correlation ID context variable for request tracing
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""
    def filter(self, record):
        record.correlation_id = correlation_id_var.get("")
        return True

# Configure logging with correlation ID
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(correlation_id)s] %(name)s: %(message)s"
)
for handler in logging.root.handlers:
    handler.addFilter(CorrelationIdFilter())

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to add correlation ID to each request."""
    
    async def dispatch(self, request: Request, call_next):
        # Get correlation ID from header or generate new one
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4())[:8])
        correlation_id_var.set(correlation_id)
        
        # Record start time
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Add correlation ID and timing to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        
        # Log request
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s"
        )
        
        return response


app = FastAPI(
    title="Scalable RAG Ingestion API",
    description="Document ingestion and search service for RAG systems with multi-tenancy support",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add correlation ID middleware (must be first)
app.add_middleware(CorrelationIdMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    error_trace = traceback.format_exc()
    logger.error(f"Unhandled exception: {exc}\n{error_trace}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )

# Include routers
app.include_router(upload.router)
app.include_router(search.router)
app.include_router(status.router)
app.include_router(diagnostics.router)
app.include_router(internal.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Scalable RAG Ingestion API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
