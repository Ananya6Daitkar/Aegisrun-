FROM python:3.12.8-slim-bookworm
WORKDIR /app
COPY . .
CMD ["python", "-m", "aegisrun", "run", "--scenario", "valid-ticket"]
