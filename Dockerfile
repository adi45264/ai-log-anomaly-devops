FROM python:3.11-slim

# Create a non-root user and group
RUN addgroup --system appgroup && adduser --system --group appuser

WORKDIR /usr/src/app

# Copy requirements and install dependencies
COPY app/requirements.txt ./app/
RUN pip install --no-cache-dir -r app/requirements.txt

# Copy application files
COPY app/ ./app/
COPY pytest.ini ./

# Change ownership of the directory
RUN chown -R appuser:appgroup /usr/src/app

# Switch to the non-root user
USER appuser

# Ensure logs are emitted immediately to stdout/stderr
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

