FROM node:22-alpine

RUN apk add --no-cache \
    ffmpeg \
    python3 \
    py3-pip \
    bash \
    curl \
    fontconfig \
    ttf-freefont \
    ttf-dejavu \
    build-base \
    && fc-cache -fv

RUN npm install -g n8n@2.29.7 --omit=dev && \
    npm cache clean --force

COPY n8n-custom-nodes/n8n-nodes-clipcraft/ /tmp/n8n-nodes-clipcraft/
RUN cd /tmp/n8n-nodes-clipcraft && \
    npm test && \
    npm run build && \
    mkdir -p /opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft && \
    cp package.json README.md /opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/ && \
    cp -R dist /opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/ && \
    rm -rf /tmp/n8n-nodes-clipcraft

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN mkdir -p /opt/video-tools /data/jobs /data/music /data/fonts

COPY video-tools/ /opt/video-tools/
RUN chmod +x /opt/video-tools/generate-video.sh \
             /opt/video-tools/render_video.py \
             /opt/video-tools/validate_manifest.py \
             /opt/video-tools/build_filters.py \
             /opt/video-tools/render-test.sh

RUN chown -R node:node /data /opt/video-tools /opt/venv /home/node

USER node

EXPOSE 5678

ENV PYTHONPATH=/opt/video-tools \
    N8N_CUSTOM_EXTENSIONS=/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/dist \
    N8N_BLOCK_ENV_ACCESS_IN_NODE=false \
    N8N_PORT=5678 \
    N8N_PROTOCOL=http \
    N8N_HOST=localhost \
    N8N_ENCRYPTION_KEY= \
    N8N_METRICS=false \
    N8N_SKIP_WEBHOOK_DEREGISTRATION_SHUTDOWN=true \
    EXECUTIONS_DATA_PRUNE=true \
    EXECUTIONS_DATA_MAX_AGE=168 \
    GENERIC_TIMEZONE=Asia/Manila \
    TZ=Asia/Manila

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f http://localhost:5678/healthz || exit 1

ENTRYPOINT ["n8n", "start"]
