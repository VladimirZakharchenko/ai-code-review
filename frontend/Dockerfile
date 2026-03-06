FROM node:20-alpine AS base

WORKDIR /app

COPY frontend/package.json frontend/vite.config.js frontend/index.html /app/
COPY frontend/src /app/src

RUN npm install

EXPOSE 4173

CMD ["npm", "run", "dev"]

