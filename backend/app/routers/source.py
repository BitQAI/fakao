from fastapi import APIRouter, Depends, HTTPException

from app import cases, config, db, statutes

router = APIRouter(prefix="/api", tags=["source"])


@router.get("/source")
def get_source(ref: str, loc: str = "", conn=Depends(db.get_db)):
    if ref in cases.CASE_SOURCES:
        rec = cases.get_case(conn, ref, loc)
        if rec is None:
            raise HTTPException(404, "案例不存在")
        return {"kind": "case", **rec}
    src_file = next(config.SOURCE_DIR.glob(f"**/{ref}"), None)
    if src_file is None or not src_file.exists():
        raise HTTPException(404, "来源文件不存在")
    text = src_file.read_text(encoding="utf-8-sig")
    offset = None
    paragraph = ""
    if loc:
        idx = text.find(loc)
        if idx != -1:
            offset = idx
            start = text.rfind("\n", 0, idx) + 1
            end = text.find("\n", idx)
            if end == -1:
                end = len(text)
            paragraph = text[start:end]
    return {"kind": "file", "ref": ref, "loc": loc,
            "title": src_file.name, "text": paragraph or text, "offset": offset}


@router.get("/statute")
def get_statute(law: str, no: str):
    no = no.strip()
    ref = f"{law}{no}" if "条" in no else f"{law}第{no}条"
    text = statutes.resolve_statute(ref)
    if text is None:
        raise HTTPException(404, "法条未收录")
    return {"law": law, "no": no, "text": text}
