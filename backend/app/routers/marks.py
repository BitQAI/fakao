"""听学标记（服务端收藏）：供听学标记、错题 tab「我的标记」与速记本使用。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import db, service

router = APIRouter(prefix="/api", tags=["marks"])


class MarkIn(BaseModel):
    entry_id: str


def _items(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, entry_id, created_at FROM marks "
        "ORDER BY created_at DESC, id DESC"
    ).fetchall()
    ids = [r["entry_id"] for r in rows]
    by_id: dict[str, dict] = {}
    if ids:
        placeholders = ",".join("?" * len(ids))
        for r in conn.execute(
            f"SELECT * FROM entries WHERE id IN ({placeholders}) AND status='final'",
            ids,
        ).fetchall():
            by_id[r["id"]] = service._entry_dict(r)
    out = []
    for r in rows:
        e = by_id.get(r["entry_id"])
        if e is None:
            continue
        out.append({"id": r["id"], "entry_id": r["entry_id"],
                    "created_at": r["created_at"], "entry": e})
    return out


@router.get("/marks")
def list_marks(conn=Depends(db.get_db)):
    return {"items": _items(conn)}


@router.post("/marks")
def add_mark(payload: MarkIn, conn=Depends(db.get_db)):
    e = conn.execute("SELECT id FROM entries WHERE id=? AND status='final'",
                     (payload.entry_id,)).fetchone()
    if e is None:
        raise HTTPException(404, "条目不存在")
    existing = conn.execute("SELECT id FROM marks WHERE entry_id=?",
                            (payload.entry_id,)).fetchone()
    if existing:
        return {"id": existing["id"], "entry_id": payload.entry_id}
    cur = conn.execute(
        "INSERT INTO marks (entry_id, created_at) VALUES (?,?)",
        (payload.entry_id, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return {"id": cur.lastrowid, "entry_id": payload.entry_id}


@router.delete("/marks/{mark_id}")
def delete_mark(mark_id: int, conn=Depends(db.get_db)):
    cur = conn.execute("DELETE FROM marks WHERE id=?", (mark_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "标记不存在")
    return {"ok": True}


@router.delete("/marks")
def clear_marks(conn=Depends(db.get_db)):
    conn.execute("DELETE FROM marks")
    conn.commit()
    return {"ok": True}
