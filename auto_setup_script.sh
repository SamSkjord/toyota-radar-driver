#!/bin/bash

# Automated setup script for Waveshare CAN HAT on Raspberry Pi
# For Toyota Radar Control

set -e

echo "=============================================="
echo "Waveshare CAN HAT Setup for Raspberry Pi"
echo "Toyota Radar Control Configuration"
echo "=============================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Detect Raspberry Pi model
echo "Detecting Raspberry Pi model..."
PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
echo "Detected: $PI_MODEL"
echo ""

# Prompt for oscillator frequency
echo "Select your Waveshare CAN HAT oscillator frequency:"
echo "1) 8 MHz"
echo "2) 12 MHz (most common)"
echo "3) 16 MHz"
echo "4) Skip (already configured)"
read -p "Enter choice [1-4]: " osc_choice

case $osc_choice in
    1) OSC_FREQ=8000000 ;;
    2) OSC_FREQ=12000000 ;;
    3) OSC_FREQ=16000000 ;;
    4) echo "Skipping oscillator configuration" ;;
    *) echo "Invalid choice. Defaulting to 12 MHz"; OSC_FREQ=12000000 ;;
esac

# Backup config.txt
if [ -f /boot/config.txt ]; then
    echo "Backing up /boot/config.txt..."
    cp /boot/config.txt /boot/config.txt.backup.$(date +%Y%m%d_%H%M%S)
fi

# Configure /boot/config.txt for MCP2515
if [ ! -z "$OSC_FREQ" ]; then
    echo "Configuring /boot/config.txt..."
    
    # Remove old CAN configurations if they exist
    sed -i '/dtoverlay=mcp2515/d' /boot/config.txt
    sed -i '/dtparam=spi=/d' /boot/config.txt
    
    # Add SPI and CAN configuration
    if ! grep -q "dtparam=spi=on" /boot/config.txt; then
        echo "dtparam=spi=on" >> /boot/config.txt
    fi
    
    echo "dtoverlay=mcp2515-can0,oscillator=$OSC_FREQ,interrupt=25" >> /boot/config.txt
    echo "dtoverlay=mcp2515-can1,oscillator=$OSC_FREQ,interrupt=24" >> /boot/config.txt
    
    echo "✓ /boot/config.txt configured"
fi

# Install required packages
echo ""
echo "Installing required packages..."
apt-get update
apt-get install -y can-utils python3-pip git

# Install Python packages
echo ""
echo "Installing Python dependencies..."
pip3 install python-can cantools

# Create CAN interface setup script
echo ""
echo "Creating CAN interface setup script..."
cat > /usr/local/bin/setup-can.sh << 'EOF'
#!/bin/bash
# Setup CAN interfaces for Toyota Radar

ip link set can0 down 2>/dev/null || true
ip link set can1 down 2>/dev/null || true

sleep 0.5

ip link set can0 type can bitrate 500000
ip link set can0 up

ip link set can1 type can bitrate 500000
ip link set can1 up

echo "CAN interfaces configured:"
ip link show can0
ip link show can1
EOF

chmod +x /usr/local/bin/setup-can.sh
echo "✓ Setup script created at /usr/local/bin/setup-can.sh"

# Create systemd service
echo ""
echo "Creating systemd service..."
cat > /etc/systemd/system/can-setup.service << 'EOF'
[Unit]
Description=Setup CAN interfaces for Toyota Radar
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/setup-can.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable can-setup.service
echo "✓ Systemd service created and enabled"

# Create CAN test script
echo ""
echo "Creating CAN test utility..."
cat > /usr/local/bin/test-can.sh << 'EOF'
#!/bin/bash
# Test CAN interfaces

echo "=== CAN Interface Status ==="
echo ""
echo "CAN0:"
ip -details link show can0
echo ""
echo "CAN1:"
ip -details link show can1
echo ""
echo "=== CAN Statistics ==="
echo ""
echo "CAN0 stats:"
ip -statistics link show can0
echo ""
echo "CAN1 stats:"
ip -statistics link show can1
echo ""
echo "=== Kernel Modules ==="
lsmod | grep -E "can|mcp"
EOF

chmod +x /usr/local/bin/test-can.sh
echo "✓ Test utility created at /usr/local/bin/test-can.sh"

# Clone repository if not already present
echo ""
read -p "Clone toyoyta_radar_control_can repository? (y/n): " clone_repo
if [ "$clone_repo" = "y" ] || [ "$clone_repo" = "Y" ]; then
    REPO_DIR="/home/pi/toyoyta_radar_control_can"
    if [ -d "$REPO_DIR" ]; then
        echo "Repository already exists at $REPO_DIR"
    else
        echo "Cloning repository..."
        su - pi -c "cd ~ && git clone https://github.com/frk2/toyoyta_radar_control_can.git"
        su - pi -c "cd ~/toyoyta_radar_control_can && git submodule update --init"
        echo "✓ Repository cloned to $REPO_DIR"
    fi
fi

# Summary
echo ""
echo "=============================================="
echo "Setup Complete!"
echo "=============================================="
echo ""
echo "Configuration summary:"
echo "  - SPI enabled"
if [ ! -z "$OSC_FREQ" ]; then
    echo "  - MCP2515 oscillator: $OSC_FREQ Hz"
fi
echo "  - CAN bitrate: 500000 bps"
echo "  - Interfaces: can0, can1"
echo ""
echo "Next steps:"
echo "  1. Reboot the system: sudo reboot"
echo "  2. After reboot, test CAN interfaces: test-can.sh"
echo "  3. Connect your Toyota radar following the wiring guide"
echo "  4. Run the control script: cd ~/toyoyta_radar_control_can && sudo python3 spoof_dsu.py"
echo ""
echo "Useful commands:"
echo "  - View CAN status: test-can.sh"
echo "  - Monitor CAN bus: candump can0"
echo "  - Send test message: cansend can0 123#DEADBEEF"
echo ""
echo "⚠️  IMPORTANT: A system reboot is required for changes to take effect!"
echo ""
read -p "Reboot now? (y/n): " do_reboot
if [ "$do_reboot" = "y" ] || [ "$do_reboot" = "Y" ]; then
    echo "Rebooting in 3 seconds..."
    sleep 3
    reboot
else
    echo "Please reboot manually when ready: sudo reboot"
fi
