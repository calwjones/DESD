from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from model_upload import ModelManager
from interaction_logger import InteractionLogger
from quality_grader import QualityGrader
from explainer import Explainer


class OverrideRequest(BaseModel):
    original_log_id: Optional[int] = None
    corrected_grade: str
    product_id: int
    user_id: Optional[int] = None

model_manager = ModelManager()
logger = InteractionLogger()
grader = QualityGrader(model_manager)
explainer = Explainer(model_manager, grader)


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_manager.load_latest()
    yield


app = FastAPI(title="BRFN AI Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "active_model": model_manager.active_version}


@app.post("/grade")
async def grade_product(
    image: UploadFile = File(...),
    product_id: int = Form(...),
    user_id: int = Form(None),
):
    if not model_manager.is_loaded():
        raise HTTPException(status_code=503, detail="No model loaded. Upload a model first.")

    image_bytes = await image.read()
    result = grader.grade(image_bytes)

    log_id = logger.log(
        service_type="quality",
        user_id=user_id,
        input_data={"product_id": product_id, "filename": image.filename},
        prediction=result,
        model_version=model_manager.active_version,
        confidence_score=result.get("confidence"),
    )

    return {**result, "log_id": log_id}


@app.post("/upload-model")
async def upload_model(
    model_file: UploadFile = File(...),
    version: str = Form(...),
    accuracy: float = Form(None),
    f1_score: float = Form(None),
    notes: str = Form(None),
):
    allowed_extensions = {".keras", ".h5", ".pkl"}
    filename = model_file.filename
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""

    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'.")

    model_bytes = await model_file.read()
    metadata = model_manager.save_and_load(
        model_bytes=model_bytes,
        filename=filename,
        version=version,
        metrics={"accuracy": accuracy, "f1_score": f1_score},
        notes=notes or "",
    )

    return {
        "message": "Model uploaded and activated successfully.",
        "version": metadata["version"],
        "activated_at": metadata["uploaded_at"],
    }


@app.get("/models")
def list_models():
    return model_manager.list_versions()


@app.get("/interactions")
def get_interactions(
    service_type: str = None,
    start_date: str = None,
    end_date: str = None,
    overrides_only: bool = False,
):
    return logger.fetch_logs(
        service_type=service_type,
        start_date=start_date,
        end_date=end_date,
        overrides_only=overrides_only,
    )

@app.post("/explain")
async def explain_prediction(
    image: UploadFile = File(...),
    product_id: int = Form(...),
    user_id: int = Form(None),
):
    if not model_manager.is_loaded():
        raise HTTPException(status_code=503, detail="No model loaded. Upload a model first.")

    image_bytes = await image.read()
    explanation = explainer.generate_gradcam(image_bytes)

    log_id = logger.log(
        service_type="quality",
        user_id=user_id,
        input_data={"product_id": product_id, "filename": image.filename},
        prediction=explanation,
        model_version=model_manager.active_version,
        confidence_score=explanation.get("confidence"),
    )

    return {**explanation, "log_id": log_id}


@app.post("/override")
def record_override(request: OverrideRequest):
    if request.corrected_grade not in {"A", "B", "C"}:
        raise HTTPException(status_code=400, detail="corrected_grade must be A, B, or C.")

    override_log_id = logger.log_override(
        original_log_id=request.original_log_id,
        corrected_grade=request.corrected_grade,
        user_id=request.user_id,
        product_id=request.product_id,
    )
    return {"status": "recorded", "override_log_id": override_log_id}

if __name__ == "__main__":
    uvicorn.run("service:app", host="0.0.0.0", port=8001, reload=True)
