FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# supergateway: bridges stdio MCP servers to HTTP (streamableHttp at /mcp)
# Add tool packages here as needed
RUN npm install -g \
    supergateway \
    @openbnb/mcp-server-airbnb

# To add more MCP tool packages to this server, append lines like:
#   RUN npm install -g @modelcontextprotocol/server-brave-search
#   RUN npm install -g @modelcontextprotocol/server-fetch
#   RUN npm install -g @modelcontextprotocol/server-filesystem

EXPOSE 8080

# --outputTransport streamableHttp → serves at POST /mcp
# Change --stdio arg to swap the underlying MCP server
CMD ["supergateway", \
     "--port", "8080", \
     "--outputTransport", "streamableHttp", \
     "--healthEndpoint", "/health", \
     "--stdio", "npx @openbnb/mcp-server-airbnb --ignore-robots-txt"]
