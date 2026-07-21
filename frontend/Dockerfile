FROM node:20-alpine

WORKDIR /app

# Install deps first so this layer is cached across code-only changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host exposes the dev server outside the container; compose bind-mounts
# the source directory over this for hot reload.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
