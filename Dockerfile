# --- Stage 1: Build the React Frontend ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --- Stage 2: Build the Python Backend ---
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (cached layer — only reruns when requirements.txt changes)
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Install the jobscraper package so `jobscraper.server` is importable
COPY src/ ./src/
RUN pip install --no-deps -e .

# Copy remaining source files
COPY . .

# Copy the built React assets from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

ENV PORT=8080
EXPOSE $PORT

# sh -c ensures ${PORT:-8080} is expanded by the shell before uvicorn sees it
CMD ["sh", "-c", "uvicorn jobscraper.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
