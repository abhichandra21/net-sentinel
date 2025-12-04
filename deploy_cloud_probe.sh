#!/bin/bash
# Deploy Cloud Probe to VPS
# Usage: ./deploy_cloud_probe.sh <YOUR_HOME_PUBLIC_IP_OR_DDNS>

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <home-public-ip-or-ddns>"
    echo "Example: $0 home.example.com"
    exit 1
fi

HOME_TARGET="$1"
VPS_HOST="ubuntu@ssh-day1.abhichandra.com"
SSH_KEY="~/.ssh/aws.pub"

echo "🚀 Deploying Cloud Probe to VPS..."

# Copy cloud probe script
echo "📤 Copying cloud_probe/main.py to VPS..."
scp -i "$SSH_KEY" cloud_probe/main.py "$VPS_HOST:~/cloud-probe/main.py"

# Create systemd service
echo "⚙️  Creating systemd service..."
ssh -i "$SSH_KEY" "$VPS_HOST" << EOF
    # Install dependencies if not already installed
    pip3 install --user requests ping3 2>/dev/null || true

    # Create systemd service
    sudo tee /etc/systemd/system/cloud-probe.service > /dev/null << 'SERVICE'
[Unit]
Description=Internet Monitor Cloud Probe
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/cloud-probe
ExecStart=/usr/bin/python3 /home/ubuntu/cloud-probe/main.py \
    --target $HOME_TARGET \
    --webhook http://192.168.1.50:8123/api/webhook/net-sentinel-cloud-probe-2025 \
    --interval 60
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

    # Reload and start service
    sudo systemctl daemon-reload
    sudo systemctl enable cloud-probe
    sudo systemctl restart cloud-probe

    echo "✅ Cloud probe deployed!"
    echo ""
    echo "Status:"
    sudo systemctl status cloud-probe --no-pager
EOF

echo ""
echo "✅ Deployment complete!"
echo ""
echo "View logs with:"
echo "  ssh -i $SSH_KEY $VPS_HOST 'sudo journalctl -u cloud-probe -f'"
