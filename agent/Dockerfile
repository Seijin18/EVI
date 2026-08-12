FROM python:3.11-slim

WORKDIR /app

# Copied before the source so a code edit does not reinstall the whole stack.
# Pins are frozen from a verified build — see openspec/specs/providers/spec.md
# (SCN-OPS-05). Refresh with:
#   docker compose build --no-cache agent-api
#   docker run --rm --entrypoint pip evi-agent-api:latest freeze | sort > agent/requirements.txt
# then rebuild and re-run the full gate before committing the new pins.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No --reload: it is a development flag and it drops in-process session state.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
