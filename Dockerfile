# Multi-stage Dockerfile for MCPUniverse
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y

# Install build tools
RUN apt install -y libpq-dev gcc g++

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Install additional dependencies for MCP servers
RUN pip install playwright
RUN playwright install chromium