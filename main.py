from contextlib import asynccontextmanager
import logging
from fastapi import HTTPException, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
from starlette.responses import StreamingResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

APP_NAME = 'archive-org-proxy'

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info(f"{APP_NAME} is starting up...")
        yield
    finally:
        logger.info(f"{APP_NAME} is shutting down...")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.middleware("http")
async def add_logging(request: Request, call_next):
    logger.info(f"Received request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status code: {response.status_code}")
    return response

@app.get("/proxy/{full_path:path}")
async def proxy(full_path: str, request:Request,  response: Response):
    parts = full_path.split('/', 1)
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid path format. Expected format: '{host}/{path}'")
    host, sub_path = parts[0], parts[1]
    if not host.endswith('archive.org'):
        raise HTTPException(status_code=403, detail="Host not allowed")
    
    target_url = f"https://{host}/{sub_path}"
    headers = {}

    # Forward Range header if present
    range_header = request.headers.get('Range')
    if range_header:
        headers['Range'] = range_header

    async with httpx.AsyncClient(follow_redirects=True) as client:
        res = await client.get(target_url, headers=headers)

        if res.status_code == 302 and "location" in res.headers:
            redirect_url = res.headers["location"]
            res = await client.get(redirect_url, headers=headers)
        
        response_headers = {
            "Content-Type": res.headers.get("content-type", "application/octet-stream"),
            "Content-Length": res.headers.get("content-length", ""),
        }
        if "content-range" in res.headers:
            response_headers["Content-Range"] = res.headers["content-range"]
        if "accept-ranges" in res.headers:
            response_headers["Accept-Ranges"] = res.headers["accept-ranges"]

        return StreamingResponse(res.aiter_bytes(), status_code=res.status_code, headers=response_headers)