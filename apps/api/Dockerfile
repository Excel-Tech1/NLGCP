FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY apps/api/src ./apps/api/src
RUN pip install --no-cache-dir .

USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "nlgcp_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
