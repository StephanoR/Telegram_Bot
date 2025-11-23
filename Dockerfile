# Use lightweight Python as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy all bot files into container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Environment variables (you will set real values in Cloud Run)
ENV BOT_TOKEN=""
ENV GOOGLE_CREDENTIALS_JSON=""

# Command to start the bot
CMD ["python", "bot.py"]
