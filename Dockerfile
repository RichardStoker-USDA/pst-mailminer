FROM python:3.10-slim

# Install libpst and other dependencies
RUN apt-get update && apt-get install -y \
    pst-utils \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p uploads results && \
    chmod 777 uploads results

# Create a non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Change ownership of the application directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5050

# Define environment variables
ENV FLASK_APP=app.py
ENV DOCKER_CONTAINER=true
# Preloaded API key for convenience
ARG PRELOADED_API_KEY
ENV PRELOADED_API_KEY=$PRELOADED_API_KEY
ARG ALLOWED_MODELS_WITH_PRELOADED_KEY="gpt-4o,gpt-4o-mini"
ENV ALLOWED_MODELS_WITH_PRELOADED_KEY=$ALLOWED_MODELS_WITH_PRELOADED_KEY

# Run the application
CMD ["python", "app.py"]