from fastapi import FastAPI

from api.routes import employees, timesheets

app = FastAPI(title="HR API")
app.include_router(employees.router)
app.include_router(timesheets.router)


@app.get("/health")
def health():
    return {"status": "ok"}
