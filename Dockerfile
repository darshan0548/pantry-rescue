FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pantry ./pantry
ENV PORT=8000 PANTRY_DB=/data/pantry.db
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "pantry.server"]
