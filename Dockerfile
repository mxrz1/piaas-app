# This Dockerfile builds a Python 3.12 container, installs the app’s dependencies, and copies the application code into the image.

FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy dependency list into the container
COPY requirements.txt /app/requirements.txt

# Install Python dependencies without caching to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code into the container
COPY app /app

# Define environment variables used by the application
ENV APP_CATEGORY="land"
ENV FLASK_RUN_HOST="0.0.0.0"
ENV FLASK_RUN_PORT="8000"

# Run the application with 'flask run' when the container starts
CMD ["flask", "run"]
