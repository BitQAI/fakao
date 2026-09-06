import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import ai, db, service

router = APIRouter(prefix="/api", tags=["assistant"])


class AskIn(BaseModel):
    question: str
    entry_id: str | None = None


@router.get("/assistant/history")
def chat_history(entry_id: str, limit: int = 20, conn=Depends(db.get_db)):
    if not entry_id.strip():
        raise HTTPException(400, "entry_id 不能为空")
    return {"items": service.chat_history_for_entry(conn, entry_id.strip(), limit)}


@router.post("/assistant/ask")
def ask(payload: AskIn, conn=Depends(db.get_db)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    context, related_ids, source_refs = service.assistant_context(
        conn, question, payload.entry_id
    )
    # 请求级连接在流式响应期间可能已被依赖关闭，日志写入用同库新连接
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()["file"])

    async def gen():
        parts = []
        async for delta in ai.stream_answer(question, context):
            parts.append(delta)
            yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        log_conn = db.connect(db_path)
        try:
            service.record_chat(log_conn, question, "".join(parts),
                                related_ids, source_refs)
        finally:
            log_conn.close()

    return StreamingResponse(gen(), media_type="text/event-stream")
