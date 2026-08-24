# El frontend: se compila con Node y se sirve con nginx.
#
# En la imagen final no queda ni Node ni node_modules, solo los ficheros
# estaticos y el servidor. Son unos 50 MB en vez de 400.

FROM node:24.13.0-alpine AS construye
WORKDIR /app
# Primero el manifiesto: mientras no cambie, esta capa se reaprovecha.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
COPY --from=construye /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1/ || exit 1
