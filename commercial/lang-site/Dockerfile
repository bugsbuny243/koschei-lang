FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html security-guide.html security-guide.tr.html robots.txt sitemap.xml /usr/share/nginx/html/
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 CMD wget -q --spider http://127.0.0.1:8080/ || exit 1
