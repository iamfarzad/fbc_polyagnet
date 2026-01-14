FROM python:3.9

COPY . /home
WORKDIR /home

RUN pip3 install -r requirements.txt

CMD ["python3", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

