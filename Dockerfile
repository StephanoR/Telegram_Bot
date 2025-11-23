# Copy your bot code and credentials into the image
COPY bot.py /app/bot.py
COPY credentials.json /app/credentials.json
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the command to run your bot
CMD ["python", "bot.py"]
