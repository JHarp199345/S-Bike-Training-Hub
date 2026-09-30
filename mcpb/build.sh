#!/bin/sh
# Build the MCP bundle (.mcpb = a zip of manifest.json + the server) and print its SHA-256 for server.json.
set -e
cd "$(dirname "$0")"
V=$(python3 -c "import json; print(json.load(open('manifest.json'))['version'])")
rm -rf build && mkdir -p build/server
cp manifest.json build/ && cp ../mcp_server.py build/server/
(cd build && zip -qrX "../s-bike-hub-mcp-$V.mcpb" manifest.json server)
rm -rf build
shasum -a 256 "s-bike-hub-mcp-$V.mcpb"
