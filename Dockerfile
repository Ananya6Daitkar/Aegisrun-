FROM python:3.12-slim
WORKDIR /app
COPY . .
CMD ["python", "-m", "aegisrun", "run", "--scenario", "valid-ticket"]
