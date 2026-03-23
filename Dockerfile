# --- Stage 1: Build the React Frontend ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Install dependencies
COPY frontend/package*.json ./
RUN npm ci

# Copy the rest of the frontend code and build
COPY frontend/ ./
RUN npm run build


# --- Stage 2: Build the Python Backend ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (gcc is often needed for some python packages like psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source code
COPY . .

# Copy the built React assets from the first stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Railway will inject the PORT environment variable at runtime.
# We set a default here just in case.
ENV PORT=8080

# Expose the port (optional but good practice for documentation)
EXPOSE $PORT

# Run Gunicorn explicitly through sh to ensure environment variables are evaluated
CMD ["sh", "-c", "gunicorn -w 1 -b 0.0.0.0:${PORT:-8080} server:app"]
