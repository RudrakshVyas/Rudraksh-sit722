FROM nginx:alpine
# Use our nginx config (optional but recommended)
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Static assets
COPY index.html /usr/share/nginx/html/index.html
COPY main.js   /usr/share/nginx/html/main.js
EXPOSE 80
