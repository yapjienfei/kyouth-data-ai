# Use an official Python runtime with uv pre-installed
# bookworm is Debian 12, a stable Linux distribution
FROM python:3.14-slim-bookworm

RUN pip install uv==0.8.0

# Set the working directory inside the container
# All following commands will run from this directory
WORKDIR /app

# Copy dependency files first (better for caching)
# We copy these separately so Docker can cache the dependency installation
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# --frozen: Use exactly the versions from uv.lock (don't update)
# --no-dev: Don't install development dependencies
RUN uv sync --frozen --no-dev

# Copy the rest of the application code
# The .dockerignore file should exclude things like __pycache__, .git, etc.
COPY src/ ./src/

# Tell Docker that the container will listen on port 8000
# This doesn't actually publish the port, it's just documentation
EXPOSE 8000

# Set the default command to run when the container starts
# ENTRYPOINT: The main command to run
# CMD: Arguments passed to the entrypoint
ENTRYPOINT ["uv", "run", "uvicorn"]
CMD ["--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "main:app"]