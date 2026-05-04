FROM mcr.microsoft.com/playwright:v1.49.0-jammy

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# supergateway bridges stdio @playwright/mcp to streamableHttp at /mcp
RUN npm install -g supergateway @playwright/mcp

# Install the browser distribution that @playwright/mcp requires
RUN npx @playwright/mcp install-browser chrome-for-testing

EXPOSE 8080

CMD ["supergateway", \
     "--port", "8080", \
     "--outputTransport", "streamableHttp", \
     "--healthEndpoint", "/health", \
     "--stdio", "npx @playwright/mcp --headless --browser chromium --isolated"]
