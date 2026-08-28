from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app import db, tts

router = APIRouter(prefix="/api", tags=["audio"])


@router.get("/audio/{entry_id}")
def get_audio(entry_id: str, conn=Depends(db.get_db)):
    row = conn.execute("SELECT id, tts_text FROM entries WHERE id=?",
                       (entry_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "条目不存在")
    path = tts.ensure_mp3(entry_id, row["tts_text"])
    if not path.exists():
        raise HTTPException(503, "音频生成中，请稍后重试")
    media_type = "audio/wav" if path.suffix == ".wav" else "audio/mpeg"
    return FileResponse(path, media_type=media_type)
