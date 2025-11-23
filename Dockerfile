# Base Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy all files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable placeholders
ENV BOT_TOKEN=""
ENV GOOGLE_CREDENTIALS_JSON=""

# Start bot
CMD ["python", "bot.py"]
