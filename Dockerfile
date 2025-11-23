# ------------------ Dockerfile ------------------
# Use Python 3.13 slim image
FROM python:3.13-slim

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy requirements first (to leverage caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files (bot.py, credentials.json, etc.)
COPY . .

# Expose the Cloud Run port
ENV PORT=8080
EXPOSE 8080

# Command to run the bot
CMD ["python", "bot.py"]
