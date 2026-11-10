from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import ConflictError, NotFoundError
from app.routers import appointments, specialties

# The application object. Uvicorn (the server) imports this and
# routes every incoming HTTP request to it.
app = FastAPI(title="MediAgent")

app.include_router(specialties.router)
app.include_router(appointments.router)


# Translate domain errors (business terms) into HTTP status codes (web terms).
# This is the ONE place where that mapping lives.
@app.exception_handler(NotFoundError)
def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(ConflictError)
def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.message})


# A decorator registers the function below as the handler for
# GET /health. FastAPI turns the returned dict into JSON.
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
