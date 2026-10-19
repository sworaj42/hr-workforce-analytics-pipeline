from fastapi import FastAPI

from api.routes import auth, employees, timesheets

app = FastAPI(title="HR API")
app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(timesheets.router)


# Public, so a load balancer or Docker can check the API without a token.
@app.get("/health")
def health():
    return {"status": "ok"}
