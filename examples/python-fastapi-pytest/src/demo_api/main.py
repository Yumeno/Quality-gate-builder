"""Minimal FastAPI application for the qgb example pack."""

from fastapi import FastAPI

app = FastAPI(title="demo-api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/greet/{name}")
def greet(name: str):
    return {"message": f"Hello, {name}!"}
