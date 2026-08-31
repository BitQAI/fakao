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
    # Web 导入面向最终用户：导入即 final（维护脚本 import_entries.py 不受影响）
    payload["status"] = "final"
    result = importer.import_payload(conn, payload)
    if result["errors"]:
        raise HTTPException(422, detail={"errors": result["errors"][:20]})
    return result
