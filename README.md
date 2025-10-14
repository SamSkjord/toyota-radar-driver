# Toyota Radar Control - Raspberry Pi Setup Guide

This guide will help you set up the Toyota radar control system on a Raspberry Pi with a Waveshare dual CAN hat.

## Hardware Requirements

- Raspberry Pi (3/4/5 recommended)
- Waveshare RS485 CAN HAT or 2-CH CAN HAT
- Toyota radar unit (2016+ with TSS - Corolla, RAV4, Highlander, Camry)
- 12V power supply for radar
- CAN bus cables/connectors

## Waveshare CAN Hat Configuration

The Waveshare dual CAN hat uses MCP2515 CAN controllers connected via SPI.

### 1. Enable SPI Interface

```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable
```

Or edit `/boot/config.txt` directly:
```bash
sudo nano /boot/config.txt
```

Add these lines:
```
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=12000000,interrupt=25
dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=24
```

**Note**: Adjust the oscillator frequency based on your Waveshare model:
- Most Waveshare hats use 12 MHz or 16 MHz crystals
- Check your specific model documentation

### 2. Install Required Packages

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade

# Install CAN utilities
sudo apt-get install can-utils

# Install Python dependencies
sudo apt-get install python3-pip
pip3 install python-can
pip3 install cantools
```

### 3. Clone Repository

```bash
cd ~
git clone https://github.com/frk2/toyoyta_radar_control_can.git
cd toyoyta_radar_control_can
git submodule update --init
```

### 4. Configure CAN Interfaces

Create a script to automatically configure CAN interfaces on boot:

```bash
sudo nano /usr/local/bin/setup-can.sh
```

Add:
```bash
#!/bin/bash
ip link set can0 type can bitrate 500000
ip link set can0 up
ip link set can1 type can bitrate 500000
ip link set can1 up
```

Make it executable:
```bash
sudo chmod +x /usr/local/bin/setup-can.sh
```

Create a systemd service:
```bash
sudo nano /etc/systemd/system/can-setup.service
```

Add:
```ini
[Unit]
Description=Setup CAN interfaces
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/setup-can.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Enable the service:
```bash
sudo systemctl enable can-setup.service
sudo systemctl start can-setup.service
```

## Wiring Connections

### Toyota Radar Pinout
```
Pin | Function
----|------------------
1   | GND
2   | Car CAN Low
3   | Car CAN High
5   | Radar CAN High
6   | Radar CAN Low
8   | 12V VCC
```

### Waveshare to Radar Connections

**CAN0 (Car CAN Bus)**
- Connect to pins 2 (CAN Low) and 3 (CAN High) on radar

**CAN1 (Radar CAN Bus)**
- Connect to pins 5 (CAN High) and 6 (CAN Low) on radar

**Power**
- Connect 12V to pin 8
- Connect GND to pin 1

## Testing the Setup

### 1. Verify CAN Interfaces

```bash
ip link show can0
ip link show can1
```

Both should show as UP and RUNNING.

### 2. Test CAN Communication

Open two terminals:

**Terminal 1 - Listen on can0:**
```bash
candump can0
```

**Terminal 2 - Send test message on can0:**
```bash
cansend can0 123#DEADBEEF
```

You should see the message appear in Terminal 1.

### 3. Run the Radar Control Script

```bash
cd ~/toyoyta_radar_control_can
sudo python3 spoof_dsu.py
```

If successful, you should see output like:
```
Got VALID track at dist: 2.44
Got VALID track at dist: 2.4
```

## Troubleshooting

### Issue: CAN interfaces not appearing

**Check kernel modules:**
```bash
lsmod | grep can
lsmod | grep mcp
```

You should see: `can`, `can_raw`, `can_dev`, `mcp251x`

**Load modules manually if needed:**
```bash
sudo modprobe can
sudo modprobe can_raw
sudo modprobe can_dev
sudo modprobe mcp251x
```

### Issue: "Device or resource busy"

Reset the CAN interfaces:
```bash
sudo ip link set can0 down
sudo ip link set can1 down
sudo ip link set can0 up
sudo ip link set can1 up
```

### Issue: Wrong oscillator frequency

If CAN communication is unreliable, you may have the wrong oscillator setting. Check your Waveshare model and adjust in `/boot/config.txt`:

- 8 MHz: `oscillator=8000000`
- 12 MHz: `oscillator=12000000`
- 16 MHz: `oscillator=16000000`

After changes, reboot:
```bash
sudo reboot
```

### Issue: Permission denied

Make sure you're running with sudo:
```bash
sudo python3 spoof_dsu.py
```

### Checking CAN Bus Statistics

```bash
ip -details -statistics link show can0
ip -details -statistics link show can1
```

Look for errors in the output. High error counts indicate wiring or bitrate issues.

## Safety Warning

⚠️ **WARNING**: This system interfaces with automotive safety equipment. Always test in a safe environment with the vehicle stationary. Never test while driving. Understand the risks involved when working with vehicle systems.

## Additional Resources

- [Waveshare CAN HAT Wiki](https://www.waveshare.com/wiki/RS485_CAN_HAT)
- [SocketCAN Documentation](https://www.kernel.org/doc/html/latest/networking/can.html)
- [Original Repository](https://github.com/frk2/toyoyta_radar_control_can)
- [OpenPilot](https://github.com/commaai/openpilot)
