FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.lock . && useradd --create-home ops
COPY --from=frontend /ui/dist ./frontend/dist
COPY scripts ./scripts
USER ops
EXPOSE 8080
CMD ["uvicorn", "ops_center.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
