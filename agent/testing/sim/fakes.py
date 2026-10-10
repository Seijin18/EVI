"""Minimal placeholder for the sim fakes server (task 2.3 replaces it)."""
from fastapi import FastAPI

app = FastAPI(title="evi-sim-fakes")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=18080)
