# Use official Playwright image (already includes all dependencies)
FROM mcr.microsoft.com/playwright/python:v1.54.0-focal

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# Install Chromium (fonts are already included in this image)
RUN playwright install chromium

# Default command (adjust script name if different)
CMD ["python", "main.py", "-s", "restaurants in Karachi", "-t", "100"]
