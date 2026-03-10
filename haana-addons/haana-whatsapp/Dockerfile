ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache nodejs npm git

COPY whatsapp-bridge/ /app/
WORKDIR /app
RUN npm install --omit=dev

COPY rootfs/ /
