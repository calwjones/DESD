from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from prediction import OrderPredictor
from interaction_logger import InteractionLogger
from explainer import OrderExplainer

predictor = OrderPredictor()
logger = InteractionLogger()
explainer = OrderExplainer(predictor)

MODEL_VERSION = "random_forest_v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    predictor.load()
    yield


app = FastAPI(title="BRFN Order Prediction Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
    customer_id: int
    top_n: int = 5
    user_id: Optional[int] = None


class ExplainRequest(BaseModel):
    customer_id: int
    product_id: int
    user_id: Optional[int] = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "order-prediction",
        "model_loaded": predictor.is_loaded(),
    }


@app.post("/predict")
def predict(request: PredictRequest):
    if not predictor.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded.")

    recommendations = predictor.recommend(request.customer_id, top_n=request.top_n)
    if not recommendations:
        raise HTTPException(
            status_code=404,
            detail=f"No order history found for customer {request.customer_id}.",
        )

    top_confidence = recommendations[0].get("reorder_probability") if recommendations else None
    logger.log(
        service_type="demand",
        user_id=request.user_id,
        input_data={"customer_id": request.customer_id, "top_n": request.top_n},
        prediction={"recommendations": recommendations},
        model_version=MODEL_VERSION,
        confidence_score=top_confidence,
    )

    return {
        "customer_id": request.customer_id,
        "recommendations": recommendations,
    }


@app.post("/explain")
def explain(request: ExplainRequest):
    if not predictor.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded.")

    result = explainer.explain(request.customer_id, request.product_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No feature row found for customer {request.customer_id} "
                f"and product {request.product_id}."
            ),
        )

    logger.log(
        service_type="demand",
        user_id=request.user_id,
        input_data={"customer_id": request.customer_id, "product_id": request.product_id},
        prediction={
            "reorder_probability": result["reorder_probability"],
            "top_positive": result["top_positive"],
            "top_negative": result["top_negative"],
        },
        model_version=MODEL_VERSION,
        confidence_score=result["reorder_probability"],
    )

    return result


@app.get("/customers")
def customers():
    return {"customer_ids": predictor.known_customers()}


@app.get("/metadata")
def metadata():
    return predictor.metadata

@app.get("/forecast")
def forecast(days: int = 7):
    if not predictor.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded.")
    return predictor.forecast(days=days)

if __name__ == "__main__":
    uvicorn.run("service:app", host="0.0.0.0", port=8002, reload=True)
