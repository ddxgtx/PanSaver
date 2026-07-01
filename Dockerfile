# Stage 1: Build Vue Frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime Environment
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Overwrite app/static with built files from Stage 1
COPY --from=frontend-builder /app/static ./app/static
EXPOSE 5632
ENV PANSAVE_MODE=server
CMD ["python", "web_app.py"]
