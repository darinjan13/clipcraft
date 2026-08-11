FROM clipcraft-n8n-debug@sha256:35b1892f05fcb3ec9e168e7cd73bf428f6cfcde9c3b9b3423c7cbc033b59c7f3

USER root

COPY n8n-custom-nodes/n8n-nodes-clipcraft/ /tmp/n8n-nodes-clipcraft/
RUN cd /tmp/n8n-nodes-clipcraft && \
    npm test && \
    npm run build && \
    mkdir -p /opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft && \
    cp package.json README.md /opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/ && \
    cp -R dist /opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/ && \
    chown -R node:node /opt/clipcraft-n8n-nodes && \
    rm -rf /tmp/n8n-nodes-clipcraft

ENV N8N_CUSTOM_EXTENSIONS=/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/dist

USER node
