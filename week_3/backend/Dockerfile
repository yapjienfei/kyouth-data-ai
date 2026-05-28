# Use Python with uv pre-installed
FROM python:3.14.5-bookworm

RUN pip install uv==0.8.0

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Expose port (backend runs on 8001)
EXPOSE 8001

# Command to run the server
# --host 0.0.0.0 allows connections from outside the container
# --port 8001 matches what frontend expects
CMD ["uv", "run", "uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8001", "--reload", "main:app"]