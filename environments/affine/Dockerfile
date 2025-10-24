FROM rayproject/ray:latest-py312

# Install system dependencies
USER root
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
USER ray

# Set working directory
WORKDIR /app

# Copy environment files
COPY . /app/

# Install Python dependencies if requirements.txt exists
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Expose Ray client port
EXPOSE 10001

# Start Ray head node
CMD ["ray", "start", "--head", "--port=6379", "--dashboard-host=0.0.0.0", "--block"]