import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import auth, employees, timesheets

# Same format as the pipeline scripts
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="HR API")
app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(timesheets.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Only method and path: no query string, headers or body, so no tokens or passwords
    request_line = f"{request.method} {request.url.path}"
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(f"{request_line} -> 500 ({duration_ms:.0f} ms) unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    duration_ms = (time.perf_counter() - start) * 1000
    message = f"{request_line} -> {response.status_code} ({duration_ms:.0f} ms)"
    if response.status_code >= 500:
        logger.error(message)
    else:
        logger.info(message)
    return response


# Public, so a load balancer or Docker can check the API without a token.
@app.get("/health")
def health():
    return {"status": "ok"}
