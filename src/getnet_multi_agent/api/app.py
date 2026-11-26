from fastapi import FastAPI

app = FastAPI(title="Getnet Multi-Agent Support")


@app.get("/health/live")
def live() -> dict:
    return {"status": "ok"}
