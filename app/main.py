from fastapi import FastAPI

from app.config import validate_config

app = FastAPI(title="VaaniKit", version="0.1.0")


@app.get("/health")
async def health():
    is_valid, message = validate_config()
    return {"status": "ok" if is_valid else "error", "message": message}
