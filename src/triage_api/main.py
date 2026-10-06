from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from triage_api.config import settings
from triage_api.schema import Category, TriageRequest, TriageResponse, Urgency

app = FastAPI(title="Triage API", version="0.1.0")

STUB_RESPONSE = TriageResponse(
    category=Category.OTHER,
    urgency=Urgency.LOW,
    confidence=0.4,
    reason="sample STUB response",
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [{"loc": err["loc"], "msg": err["msg"], "type": err["type"]} for err in exc.errors()]
    return JSONResponse(
        status_code=400,
        content={"detail": detail},
    )

@app.get("/health")
async def health():
    return {"status": "ok"}
    
@app.post("/triage")
async def triage(req: TriageRequest) -> TriageResponse:
    if settings.llm_stub:
        return STUB_RESPONSE
    raise NotImplementedError

