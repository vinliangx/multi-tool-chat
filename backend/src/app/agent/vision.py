from langchain_core.messages import HumanMessage

from app.agent.llm import build_vision_llm


def _llm():
    return build_vision_llm()


async def vision(prompt: str, mime: str, data: str) -> str:
    """Vision read image"""
    llm = _llm()
    print(prompt, mime, data)
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{data}"},
            },
        ]
    )
    resp = llm.invoke([message])
    return str(resp.content)
