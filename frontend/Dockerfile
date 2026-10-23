FROM node:20-alpine

WORKDIR /app

# Install dependencies first (leverages Docker cache)
COPY package*.json ./
RUN npm install

# Copy source files
COPY . .

EXPOSE 5173

# Start Vite dev server accessible externally on port 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
