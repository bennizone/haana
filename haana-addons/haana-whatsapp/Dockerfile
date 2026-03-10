ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache nodejs npm

COPY whatsapp-bridge/ /app/
WORKDIR /app
RUN npm ci --omit=dev

COPY rootfs/ /
