# Toyota Radar Control - Quick Reference

## ✅ Your Setup is Working!

The script successfully:
- Detects CAN interfaces (can0 and can1)
- Loads the DBC files
- Enters the main spoofing loop
- Sends periodic messages to keep the radar alive

## Common Commands

### Run the Radar Control
```bash
cd ~/toyota-radar
sudo python3 toyota_radar_rpi.py
```

### Monitor CAN Traffic

**Watch all traffic on car CAN bus (can0):**
```bash
candump can0
```

**Watch all traffic on radar CAN bus (can1):**
```bash
candump can1
```

**Watch only radar tracking messages (0x210-0x21F):**
```bash
candump can1 | grep "210\|211\|212\|213\|214\|215\|216\|217\|218\|219\|21A\|21B\|21C\|21D\|21E"
```

**Log CAN data to file:**
```bash
candump -l can0 can1
# Creates log files: candump-YYYY-MM-DD_HHMMSS.log
```

### Check CAN Interface Status

```bash
# View interface status
ip link show can0
ip link show can1

# View statistics (errors, dropped packets, etc.)
ip -s link show can0
ip -s link show can1

# Detailed statistics
ifconfig can0
ifconfig can1
```

### Restart CAN Interfaces

If you need to reset the interfaces:
```bash
sudo ip link set can0 down
sudo ip link set can1 down
sudo ip link set can0 up
sudo ip link set can1 up
```

## What You Should See

### Successful Operation
When the radar is working, you'll see messages like:
```
Got VALID track at dist: 2.44
Got VALID track at dist: 2.4
Got VALID track at dist: 2.36
```

This means the radar is detecting objects and sending valid tracking data!

### No Tracks Detected
If you don't see "VALID track" messages:
- The radar might not be detecting any objects (point it at something)
- Check your wiring connections
- Verify power supply to radar (12V on pin 8)
- Check CAN bus termination resistors

## Troubleshooting

### Problem: "Device or resource busy"
```bash
sudo ip link set can0 down
sudo ip link set can1 down
sleep 1
sudo ip link set can0 type can bitrate 500000
sudo ip link set can1 type can bitrate 500000
sudo ip link set can0 up
sudo ip link set can1 up
```

### Problem: High error count
Check statistics:
```bash
ip -s link show can0
```

Look for RX/TX errors. High errors indicate:
- Wrong bitrate (should be 500000)
- Poor wiring/connections
- Missing termination resistors
- Interference

### Problem: Script hangs or freezes
- Press Ctrl+C to stop
- Check if CAN interfaces are still up: `ip link show can0`
- Restart the interfaces if needed

## CAN Bus Message IDs Reference

### Messages Sent TO Radar (on can0 - car bus):
- `0x141` - DSU status
- `0x128` - DSU control
- `0x283` - DSU presence
- `0x344` - DSU misc
- `0x160` - DSU state
- `0x161` - DSU info
- `0x365` - DSU parameters (RAV4/Corolla)
- `0x366` - DSU parameters (RAV4/Corolla)
- `0x4CB` - DSU heartbeat
- `0x1D2` - ACC_CONTROL
- `0x1D3` - PCM_CRUISE
- `0x1D4` - SPEED

### Messages Received FROM Radar (on can1 - radar bus):
- `0x210-0x21F` - Radar tracks (objects detected)
  - Each track contains distance, velocity, angle data
  - VALID=1 means the track is confirmed

## Hardware Wiring Reminder

```
Toyota Radar          Waveshare CAN Hat
-----------          -----------------
Pin 2 (Car CAN L) -> CAN0 L (Low)
Pin 3 (Car CAN H) -> CAN0 H (High)
Pin 5 (Radar CAN H)-> CAN1 H (High)
Pin 6 (Radar CAN L)-> CAN1 L (Low)
Pin 8 (12V)       -> 12V Power Supply
Pin 1 (GND)       -> GND
```

## Advanced: Recording and Playback

### Record CAN Traffic
```bash
# Record both buses
candump -l any,0:0,#FFFFFFFF

# Playback later
canplayer -I candump-YYYY-MM-DD_HHMMSS.log
```

### Analyze Specific Messages
```bash
# Filter by message ID (e.g., ACC_CONTROL = 0x1D2)
candump can0 | grep "1D2"

# Show timestamp
candump -t a can0
```

## System Service (Optional)

To run automatically on boot, create `/etc/systemd/system/toyota-radar.service`:

```ini
[Unit]
Description=Toyota Radar Control
After=can-setup.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/toyota-radar
ExecStart=/usr/bin/python3 /home/pi/toyota-radar/toyota_radar_rpi.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable toyota-radar.service
sudo systemctl start toyota-radar.service
```

## Safety Reminders

⚠️ **IMPORTANT**:
- Always test with the vehicle stationary
- Never rely on this for safety-critical applications
- This is for research/educational purposes only
- The radar needs proper calibration for accuracy
- Check local regulations regarding automotive modifications

## Need Help?

Check the full documentation:
- Original repo: https://github.com/frk2/toyoyta_radar_control_can
- Waveshare wiki: https://www.waveshare.com/wiki/RS485_CAN_HAT
- SocketCAN docs: https://www.kernel.org/doc/html/latest/networking/can.html
