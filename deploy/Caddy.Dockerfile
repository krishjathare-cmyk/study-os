FROM caddy:2.10-alpine

COPY Caddyfile /etc/caddy/Caddyfile
RUN addgroup -S -g 10001 studyos \
    && adduser -S -D -H -u 10001 -G studyos studyos \
    && chown -R studyos:studyos /data /config /etc/caddy

USER studyos
