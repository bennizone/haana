FROM node:22-slim

WORKDIR /app

# git wird für npm-Pakete mit Git-Abhängigkeiten benötigt (z.B. Baileys)
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global url."https://github.com/".insteadOf "ssh://git@github.com/"

# Dependencies zuerst (besseres Layer-Caching)
COPY package.json .
RUN npm install --omit=dev

COPY index.js .

# Session-Verzeichnis (wird als Volume gemountet)
RUN mkdir -p /app/session

ENV NODE_ENV=production

CMD ["node", "index.js"]
