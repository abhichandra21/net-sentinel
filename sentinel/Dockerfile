FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for ping and diagnostics
# iputils-ping, traceroute, dnsutils (dig), curl are useful for the bash diagnostics fallback
RUN apt-get update && apt-get install -y \
    iputils-ping \
    traceroute \
    dnsutils \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Run as root to allow ICMP ping without special capabilities configuration, 
# though setting capabilities is cleaner, running as root in internal docker is acceptable for this scope.
CMD ["python", "-u", "src/monitor.py"]
