FROM python:3.11-slim

# Install Node.js (needed for npx mongodb-mcp-server)
RUN apt-get update && apt-get install -y nodejs npm curl

WORKDIR /app

# Copy dependency files first (for caching)
COPY pyproject.toml uv.lock ./

# Install uv and dependencies
RUN pip install uv && uv sync --frozen

# Copy rest of the code
COPY . .

# Expose port
EXPOSE 8000

# Start the app
CMD ["uv", "run", "python", "app/agent_engine_app.py"]
