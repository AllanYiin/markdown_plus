# Markdown+ playground container.
# Used by Zeabur / Fly / Render / any Dockerfile-aware PaaS.
FROM python:3.11-slim

WORKDIR /app

# Install deps first to leverage layer cache
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the project
COPY . .

# Document the default port. Zeabur / other PaaS override via the PORT env var
# which server.py honors. Locally `docker run -p 8000:8000` works as-is.
EXPOSE 8000

# Server reads PORT env var (default 8000) and OPENAI_API_KEY from env.
CMD ["python", "server.py"]
