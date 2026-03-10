ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache nodejs npm

COPY whatsapp-bridge/ /app/
WORKDIR /app
RUN npm install --omit=dev

COPY rootfs/ /
