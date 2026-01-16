FROM python:3.9

# Create the agents directory structure in the container
WORKDIR /app
COPY agents/ ./agents/
COPY requirements.txt ./

# Install dependencies
RUN pip3 install -r requirements.txt

# Set the Python path to the root so 'agents.' imports work
ENV PYTHONPATH=/app

CMD ["python3", "-m", "uvicorn", "agents.api:app", "--host", "0.0.0.0", "--port", "8000"]

