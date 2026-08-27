from fastapi import FastAPI

from app.routers import (assistant, audio, coverage, import_, plans,
                         quizzes, reports, reviews, settings, source, today)

app = FastAPI(title="法考冲刺工具")

for router in (today.router, plans.router, reviews.router, audio.router,
               source.router, quizzes.router, reports.router, coverage.router,
               assistant.router, settings.router, import_.router):
    app.include_router(router)


@app.get("/api/health")
def health():
    return {"ok": True}
