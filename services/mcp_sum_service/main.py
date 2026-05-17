from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Sum MCP Service")


class SumRequest(BaseModel):
    a: float
    b: float


class SumResponse(BaseModel):
    result: float
    expression: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/sum", response_model=SumResponse)
async def sum_numbers(body: SumRequest) -> SumResponse:
    result = body.a + body.b
    return SumResponse(result=result, expression=f"{body.a} + {body.b} = {result}")
