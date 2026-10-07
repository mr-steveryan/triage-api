from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from triage_api.client import LLM
from triage_api.config import settings
from triage_api.schema import Category, TriageRequest, TriageResponse, Urgency

SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{settings.llm_prompt_version}.md"
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

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
    response = await LLM.chat.completions.create(
        model = settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": req.support_message}
        ],
        temperature=0.0,
        response_format={'type': 'json_schema', 'json_schema':{
            "name":"triage",
            "strict": True,
            "schema": TriageResponse.model_json_schema()
        }}
    )
    content = response.choices[0].message.content
    if content is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No content in response")
    return TriageResponse.model_validate_json(content)

