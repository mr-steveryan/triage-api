import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import openai
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import ValidationError

from triage_api.config import settings
from triage_api.llm import LLM
from triage_api.schema import Category, TriageRequest, TriageResponse, Urgency

# system constants
LLM_TIME_BUDGET_S = 30

SYSTEM_PROMPT_PATH = (
    Path(__file__).parent / "prompts" / f"{settings.llm_prompt_version}.md"
)
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

QUARANTINE_PATH = Path("logs/quarantine.jsonl")
COST_PATH = Path("logs/costs.jsonl")
QUARANTINE_PATH.parent.mkdir(exist_ok=True)

STUB_RESPONSE = TriageResponse(
    category=Category.OTHER,
    urgency=Urgency.LOW,
    confidence=0.4,
    reason="sample STUB response",
)
RESPONSE_FORMAT: ResponseFormatJSONSchema = {
    "type": "json_schema",
    "json_schema": {
        "name": "triage",
        "strict": True,
        "schema": TriageResponse.model_json_schema(),
    },
}
REPAIR_INSTRUCTION = "Your previous answer was rejected for this reason. Return only corrected JSON matching the schema."


# helper functions
def extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return text
    return text[start : end + 1]


async def ask(
    messages: list[ChatCompletionMessageParam],
) -> tuple[str, CompletionUsage | None]:
    try:
        resp = await LLM.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=settings.llm_temp,
            response_format=RESPONSE_FORMAT,
        )
    except openai.APIError as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="The model provider returned an error"
        ) from e

    content = resp.choices[0].message.content
    if content is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="The model returned an empty response",
        )
    return content, resp.usage


def parse(raw: str) -> TriageResponse:
    return TriageResponse.model_validate_json(extract_json(raw))


def jsonl_writer(
    path: Path, record: dict
) -> None:  # blocks the event loop. fix: asyncio.to_thread
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# API routes
app = FastAPI(title="Triage API", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = [
        {"loc": err["loc"], "msg": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={"detail": detail},
    )


@app.get("/health")
async def health():
    if settings.llm_kill_switch:
        return {"status": "paused"}
    return {"status": "ok"}


@app.post("/triage")
async def triage(req: TriageRequest) -> TriageResponse:
    if settings.llm_kill_switch:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The triage service is temporarily unavailable",
        )
    if settings.llm_stub:
        return STUB_RESPONSE

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": req.support_message},
    ]
    start = time.perf_counter()
    usages: list[CompletionUsage | None] = []
    need_repair = False
    try:
        async with asyncio.timeout(LLM_TIME_BUDGET_S):
            raw, usage = await ask(messages)
            usages.append(usage)
            try:
                return parse(raw)
            except ValidationError as e:
                error = str(e)
            messages.extend(
                [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"{REPAIR_INSTRUCTION}\n\n{error}"},
                ]
            )
            need_repair = True
            repair_raw, repair_usage = await ask(messages)
            usages.append(repair_usage)
            try:
                return parse(repair_raw)
            except ValidationError as e:
                jsonl_writer(
                    QUARANTINE_PATH,
                    {
                        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                        "input": req.support_message,
                        "prompt_version": settings.llm_prompt_version,
                        "response": raw,
                        "error": error,
                        "repair_response": repair_raw,
                        "repair_error": str(e),
                    },
                )
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="The model could not produce a valid triage result",
                )
    except TimeoutError as e:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, detail="The model response took too long"
        ) from e
    finally:
        reported = [u for u in usages if u is not None]
        complete = len(reported) == len(usages)
        record = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "prompt_version": settings.llm_prompt_version,
            "model_name": settings.llm_model,
            "input_tokens": sum(u.prompt_tokens for u in reported)
            if complete
            else None,
            "output_tokens": sum(u.completion_tokens for u in reported)
            if complete
            else None,
            "duration_ms": round((time.perf_counter() - start) * 1000),
            "needed_repair": need_repair,
        }
        jsonl_writer(COST_PATH, record)
