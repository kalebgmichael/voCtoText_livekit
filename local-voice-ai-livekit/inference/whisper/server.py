import logging
import os
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from faster_whisper import WhisperModel

logger = logging.getLogger("whisper-server")
logging.basicConfig(level=logging.INFO)

MODEL_ID = os.environ.get("VOXBOX_HF_REPO_ID", "Systran/faster-whisper-small")
DATA_DIR = os.environ.get("DATA_DIR", "/data")

model: Optional[WhisperModel] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    logger.info("Loading model %s into %s", MODEL_ID, DATA_DIR)
    model = WhisperModel(MODEL_ID, device="cpu", compute_type="int8", download_root=DATA_DIR)
    logger.info("Model loaded")
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model_name: Optional[str] = Form(None, alias="model"),
    language: Optional[str] = Form(None),
    response_format: Optional[str] = Form("json"),
):
    suffix = os.path.splitext(file.filename or ".wav")[1] or ".wav"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        segments, info = model.transcribe(tmp_path, language=language or None, beam_size=5)
        text = " ".join(s.text.strip() for s in segments)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return {"text": text, "model": MODEL_ID, "language": info.language}
