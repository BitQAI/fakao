import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app import db, importer

router = APIRouter(prefix="/api", tags=["import"])


@router.post("/import")
async def upload_import(file: UploadFile, conn=Depends(db.get_db)):
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "仅支持 .json 文件")
    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "JSON 解析失败")
    result = importer.import_payload(conn, payload)
    if result["errors"]:
        raise HTTPException(422, detail={"errors": result["errors"][:20]})
    return result
