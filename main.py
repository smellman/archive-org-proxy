"""archive-org-proxy: archive.org 向けのシンプルなプロキシサーバー。

エンドポイント:
    GET /proxy/{host}/{path}
        host は ``archive.org`` で終わるホスト名のみ許可。
        Range ヘッダーは透過的に転送される。

起動方法:
    Docker Compose:
        docker compose up -d              # ホストの 18080 ポートで待受
    Docker:
        docker build -t archive-org-proxy .
        docker run -p 18080:80 archive-org-proxy
    ローカル開発 (uv が必要):
        uv sync
        uv run fastapi dev main.py

使用例:
    curl http://localhost:18080/proxy/archive.org/details/example
"""

from contextlib import asynccontextmanager
import logging
from fastapi import HTTPException, FastAPI, Request
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
async def proxy(full_path: str, request: Request):
    parts = full_path.split('/', 1)
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid path format. Expected format: '{host}/{path}'")
    host, sub_path = parts[0], parts[1]
    if host != 'archive.org' and not host.endswith('.archive.org'):
        raise HTTPException(status_code=403, detail="Host not allowed")

    target_url = f"https://{host}/{sub_path}"
    headers = {}

    # Forward Range header if present
    range_header = request.headers.get('Range')
    if range_header:
        headers['Range'] = range_header

    # レスポンスボディはストリーミングで転送する。
    # client.get() だとボディ全体を読み切るまで待つため、大きなファイルでは
    # read タイムアウトに達して httpx.ReadTimeout で 500 になる。
    # connect のみ短めにし、read タイムアウトは無効化する。
    timeout = httpx.Timeout(10.0, read=None)
    client = httpx.AsyncClient(follow_redirects=True, timeout=timeout)

    req = client.build_request("GET", target_url, headers=headers)
    res = await client.send(req, stream=True)

    response_headers = {
        "Content-Type": res.headers.get("content-type", "application/octet-stream"),
    }
    if "content-length" in res.headers:
        response_headers["Content-Length"] = res.headers["content-length"]
    if "content-range" in res.headers:
        response_headers["Content-Range"] = res.headers["content-range"]
    if "accept-ranges" in res.headers:
        response_headers["Accept-Ranges"] = res.headers["accept-ranges"]

    async def body():
        try:
            async for chunk in res.aiter_bytes():
                yield chunk
        finally:
            await res.aclose()
            await client.aclose()

    return StreamingResponse(body(), status_code=res.status_code, headers=response_headers)