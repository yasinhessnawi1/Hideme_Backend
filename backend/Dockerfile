# Use an official lightweight Python image.
FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable unbuffered logging.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory in the container.
WORKDIR /backend

# Install system dependencies needed to compile packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the dependency file(s) first for caching.
COPY requirements.txt /backend/requirements.txt

# Upgrade pip and install dependencies.
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . /backend

# Expose the port that the application will run on.
EXPOSE 8000

# Command to run the FastAPI application using Uvicorn.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
