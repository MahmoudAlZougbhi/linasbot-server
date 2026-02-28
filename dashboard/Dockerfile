FROM node:20-alpine

WORKDIR /app

ENV HOST=0.0.0.0
ENV PORT=3000

# Install dependencies first for better layer caching
COPY package*.json ./
RUN npm install --legacy-peer-deps || npm install

# Copy dashboard source
COPY . .

EXPOSE 3000

CMD ["npm", "start"]
