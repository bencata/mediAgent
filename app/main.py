from fastapi import FastAPI

# The application object. Uvicorn (the server) imports this and
# routes every incoming HTTP request to it.
app = FastAPI(title="MediAgent")


# A decorator registers the function below as the handler for
# GET /health. FastAPI turns the returned dict into JSON.
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
