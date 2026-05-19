from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, unquote

import boto3
import db
import httpx
import rag_queue
import worker
from botocore.client import Config
from config import settings
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO)

_worker_task: asyncio.Task | None = None
_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(settings.reranker_model)
    return _reranker


@asynccontextmanager
async def lifespan(app):
    global _worker_task
    await db.run_migrations()
    pending = await db.get_pending_documents()
    await rag_queue.requeue_interrupted([str(d["id"]) for d in pending])
    _worker_task = asyncio.create_task(worker.worker_loop())
    try:
        yield
    finally:
        if _worker_task:
            _worker_task.cancel()
            await asyncio.gather(_worker_task, return_exceptions=True)
        await db.close_pool()
        await rag_queue.close_redis()


mcp = FastMCP("Documents RAG", lifespan=lifespan)


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.external_s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.region_name,
        config=Config(signature_version="s3v4"),
    )


def _presigned_url(s3_url: str, expiry: int = 3600) -> str:
    _, _, rest = s3_url.partition("s3://")
    bucket, _, key = rest.partition("/")
    return _s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": unquote(key)}, ExpiresIn=expiry
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool(name="rag_upload")
async def rag_upload(s3_url: str) -> dict:
    """Queue an S3 document (s3://bucket/key) for chunking and RAG indexing."""
    if not s3_url.startswith("s3://"):
        return {"error": "s3_url must start with s3://"}
    filename = s3_url.rstrip("/").split("/")[-1]
    doc_id = uuid.uuid4()
    await db.insert_document(doc_id, s3_url, filename)
    await rag_queue.enqueue(doc_id)
    queue = await db.get_queue_status()
    position = next((i + 1 for i, d in enumerate(queue) if d["id"] == str(doc_id)), 1)
    return {"job_id": str(doc_id), "filename": filename, "position_in_queue": position}


@mcp.tool(name="rag_list")
async def rag_list(search_term: str | None = None, max_documents: int = 20) -> dict:
    """List documents in the RAG index. Optionally filter by filename and cap results.

    Returns {documents, count, has_more}. If has_more is true, narrow with search_term or increase max_documents.
    """
    rows = await db.get_all_documents(search_term=search_term, limit=max_documents + 1)
    has_more = len(rows) > max_documents
    rows = rows[:max_documents]
    output = []
    for r in rows:
        try:
            link = _presigned_url(r["s3_url"])
        except Exception:
            link = r["s3_url"]
        output.append(
            {
                "job_id": r["id"],
                "filename": r["filename"],
                "original_s3_url": r["s3_url"],
                "s3_url": link,
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
                "completed_at": r["completed_at"].isoformat()
                if r["completed_at"]
                else None,
                "chunk_count": r["chunk_count"],
                "error": r["error"],
            }
        )
    return {"documents": output, "count": len(output), "has_more": has_more}


@mcp.tool(name="rag_queue_status")
async def rag_queue_status() -> list[dict]:
    """Return the ordered list of documents pending or being processed."""
    rows = await db.get_queue_status()
    return [
        {
            "job_id": r["id"],
            "s3_url": r["s3_url"],
            "filename": r["filename"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@mcp.tool(name="rag_search")
async def rag_search(
    query: str, top_k: int = 5, score_threshold: float = 0.4
) -> list[dict]:
    """Semantic search over indexed documents. Returns ranked chunks with temporary S3 links.

    score_threshold filters out vector results with cosine similarity below that value
    before RRF merging (0.0 = no filtering).
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.embedding_model, "input": query},
        )
        resp.raise_for_status()
        query_embedding = resp.json()["embeddings"][0]

    results = await db.search_chunks(query_embedding, query, top_k, score_threshold)

    if settings.use_reranker and results:
        reranker = _get_reranker()
        pairs = [(query, r["content"]) for r in results]
        scores = await asyncio.to_thread(reranker.predict, pairs)
        for r, s in zip(results, scores):
            r["rerank_score"] = float(s)
        results.sort(key=lambda r: r["rerank_score"], reverse=True)

    output = []
    for r in results:
        try:
            link = _presigned_url(r["s3_url"])
        except Exception:
            link = r["s3_url"]
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
            import json as _json

            meta = _json.loads(meta)
        output.append(
            {
                "content": meta.get("parent_text") or r["content"],
                "chunk_content": r["content"],
                "score": r.get("rerank_score", float(r["score"])),
                "filename": r["filename"],
                "s3_url": link,
                "original_s3_url": r["s3_url"],
            }
        )
    return output


@mcp.tool(name="rag_delete")
async def rag_delete(s3_url: str) -> dict:
    """Delete a document from the RAG index and remove the S3 object. s3_url must be the original s3:// URL."""
    if not s3_url.startswith("s3://"):
        return {"error": "s3_url must start with s3://"}
    result = await db.delete_document_by_s3_url(s3_url)
    if result.get("error"):
        return result
    _, _, rest = s3_url.partition("s3://")
    bucket, _, key = rest.partition("/")
    try:
        await asyncio.to_thread(
            lambda: _s3_client().delete_object(Bucket=bucket, Key=unquote(key))
        )
    except Exception as e:
        result["s3_warning"] = f"Index removed but S3 delete failed: {e}"
    return result


async def _summarize_text(text: str) -> str:
    prompt = f"Summarize the following document in 2-3 sentences:\n\n{text[:8000]}"
    if settings.vision_provider == "anthropic":
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model=settings.vision_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    else:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.vision_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["response"]


@mcp.tool(name="doc_preview")
async def doc_preview(s3_url: str) -> dict:
    """Preview a document or image from S3: returns a raw text snippet and an LLM-generated summary without indexing."""
    if not s3_url.startswith("s3://"):
        return {"error": "s3_url must start with s3://"}

    filename = s3_url.rstrip("/").split("/")[-1]
    ext = Path(filename).suffix.lower()

    try:
        data = await asyncio.to_thread(worker._download, s3_url)
    except Exception as e:
        return {"error": f"Failed to download: {e}"}

    try:
        if ext in worker._IMAGE_EXTS:
            description = await worker._describe_image(data, ext)
            return {
                "filename": filename,
                "content_type": "image",
                "snippet": description[:500],
                "summary": description,
            }
        else:
            text = worker._extract_text(data, ext)
            if not text.strip():
                return {"error": f"No text could be extracted from {filename}"}
            summary = await _summarize_text(text)
            return {
                "filename": filename,
                "content_type": "document",
                "snippet": text[:500],
                "summary": summary,
            }
    except Exception as e:
        return {"error": f"Failed to process: {e}"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8003)
