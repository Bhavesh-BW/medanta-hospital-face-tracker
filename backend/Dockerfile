FROM vision-gpu:latest
WORKDIR /app
COPY face_tracker.py /app/face_tracker.py
COPY dist /app/dist
COPY models /app/models
ENV HOST=0.0.0.0 PORT=8198 FACE_TRACKER_DB=/data/face_tracker.db RTSP_BASE=rtsp://124.123.89.162:31554/live
EXPOSE 8198
VOLUME ["/data"]
CMD ["python", "face_tracker.py"]

