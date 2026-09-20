from fastapi import FastAPI

from app.routers import (assistant, audio, cards, coverage, import_, marks,
                         plans, quizzes, reports, reviews, settings, source,
                         today, stats, statutes, wrongbook, cases_quiz)

app = FastAPI(title="法考冲刺工具")

for router in (today.router, plans.router, reviews.router, audio.router,
               source.router, quizzes.router, reports.router, coverage.router,
               assistant.router, settings.router, import_.router, marks.router,
               statutes.router, cards.router, cases_quiz.router):
    app.include_router(router)
app.include_router(wrongbook.router)
app.include_router(stats.router)


@app.get("/api/health")
def health():
    return {"ok": True}
