# Use an official lightweight Python image.
FROM python:3.12.6-slim

# Prevent Python from writing .pyc files and enable unbuffered logging.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/Hideme_Backend

# Set the working directory to the backend folder.
WORKDIR /Hideme_Backend/backend

# Install system dependencies required for building packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file.
COPY requirements.txt .

# Optionally copy the .env backup file (if it exists).
COPY .env* .

# Upgrade pip and install dependencies.
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code.
COPY . .

# Expose the port your FastAPI app will run on.
EXPOSE 8000

# Run the FastAPI app via Uvicorn.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000",  "--timeout-keep-alive", "1200", "--limit-concurrency", "100", "--workers", "2"]
