FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi uvicorn \
    langchain langgraph langchain-community \
    langchain-ollama langchain-qdrant \
    qdrant-client httpx pymupdf

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
