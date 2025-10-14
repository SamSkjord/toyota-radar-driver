#!/usr/bin/python3

import cantools
import can
import time
import sys
import os

"""
Raspberry Pi version for Waveshare Dual CAN Hat

This file assumes that:
- can0 is connected to the CAR CAN bus (pin 3/2)
- can1 is connected to the RADAR CAN bus (Pin 5/6 on the radar unit)

IMPORTANT: Before running this script, configure the CAN interfaces:
sudo ip link set can0 type can bitrate 500000
sudo ip link set can1 type can bitrate 500000
sudo ip link set can0 up
sudo ip link set can1 up

For automatic setup on boot, add to /etc/network/interfaces:
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 500000
    up /sbin/ifconfig can0 up
    down /sbin/ifconfig can0 down

auto can1
iface can1 inet manual
    pre-up /sbin/ip link set can1 type can bitrate 500000
    up /sbin/ifconfig can1 up
    down /sbin/ifconfig can1 down
"""


class OnCan(can.Listener):
    def __init__(self):
        try:
            self.db = cantools.database.load_file('opendbc/toyota_prius_2017_adas.dbc', strict=False)
        except FileNotFoundError:
            print("Warning: DBC file not found. Run: git submodule update --init")
            self.db = None
        except Exception as e:
            print(f"Warning: Could not load DBC file: {e}")
            self.db = None

    def on_message_received(self, boo):
        if 0x210 <= boo.arbitration_id < 0x21F:
            if self.db:
                try:
                    msg = self.db.decode_message(boo.arbitration_id, boo.data)
                    if msg["VALID"] == 1:
                        print("Got VALID track at dist: " + str(msg["LONG_DIST"]))
                except Exception as e:
                    pass  # Silently ignore decode errors
            else:
                # If no DBC, just print raw data
                print(f"Radar message: ID=0x{boo.arbitration_id:x}, Data={boo.data.hex()}")


class ECU:
    CAM = 0  # camera
    DSU = 1  # driving support unit
    APGS = 2  # advanced parking guidance system


class CAR:
    PRIUS = 0
    LEXUS_RXH = 1
    RAV4 = 2
    RAV4H = 3
    COROLLA = 4


# Convert strings to bytes for Python 3
STATIC_MSGS = [
    (0x141, ECU.DSU, (CAR.PRIUS, CAR.RAV4H, CAR.LEXUS_RXH, CAR.RAV4, CAR.COROLLA), 1, 2, b'\x00\x00\x00\x46'),
    (0x128, ECU.DSU, (CAR.PRIUS, CAR.RAV4H, CAR.LEXUS_RXH, CAR.RAV4, CAR.COROLLA), 1, 3, b'\xf4\x01\x90\x83\x00\x37'),
    (0x283, ECU.DSU, (CAR.PRIUS, CAR.RAV4H, CAR.LEXUS_RXH, CAR.RAV4, CAR.COROLLA), 0, 3, b'\x00\x00\x00\x00\x00\x00\x8c'),
    (0x344, ECU.DSU, (CAR.PRIUS, CAR.RAV4H, CAR.LEXUS_RXH, CAR.RAV4, CAR.COROLLA), 0, 5, b'\x00\x00\x01\x00\x00\x00\x00\x50'),
    (0x160, ECU.DSU, (CAR.PRIUS, CAR.RAV4H, CAR.LEXUS_RXH, CAR.RAV4, CAR.COROLLA), 1, 7, b'\x00\x00\x08\x12\x01\x31\x9c\x51'),
    (0x161, ECU.DSU, (CAR.PRIUS, CAR.RAV4H, CAR.LEXUS_RXH, CAR.RAV4, CAR.COROLLA), 1, 7, b'\x00\x1e\x00\x00\x00\x80\x07'),
    (0x365, ECU.DSU, (CAR.RAV4, CAR.COROLLA), 0, 20, b'\x00\x00\x00\x80\xfc\x00\x08'),
    (0x366, ECU.DSU, (CAR.RAV4, CAR.COROLLA), 0, 20, b'\x00\x72\x07\xff\x09\xfe\x00'),
    (0x4CB, ECU.DSU, (CAR.PRIUS, CAR.RAV4H, CAR.LEXUS_RXH, CAR.RAV4, CAR.COROLLA), 0, 100, b'\x0c\x00\x00\x00\x00\x00\x00\x00'),
]


def check_can_interface(interface):
    """Check if CAN interface exists and is operational"""
    try:
        result = os.system(f'ip link show {interface} > /dev/null 2>&1')
        return result == 0
    except Exception:
        return False


def setup_can_interface(interface, bitrate=500000):
    """Attempt to configure CAN interface"""
    print(f"Setting up {interface}...")
    os.system(f'sudo ip link set {interface} type can bitrate {bitrate}')
    os.system(f'sudo ip link set {interface} up')
    time.sleep(0.5)
    return check_can_interface(interface)


if __name__ == '__main__':
    print("=" * 60)
    print("Toyota Radar Control - Raspberry Pi with Waveshare CAN Hat")
    print("=" * 60)
    
    # Check if running with sudo
    if os.geteuid() != 0:
        print("WARNING: Not running as root. CAN setup may fail.")
        print("Consider running with: sudo python3 spoof_dsu.py")
        print()
    
    # Check/setup CAN interfaces
    if not check_can_interface('can0'):
        print("can0 not found. Attempting to configure...")
        if not setup_can_interface('can0'):
            print("ERROR: Failed to configure can0!")
            print("Manual setup:")
            print("  sudo ip link set can0 type can bitrate 500000")
            print("  sudo ip link set can0 up")
            sys.exit(1)
    else:
        print("✓ can0 interface detected")
    
    if not check_can_interface('can1'):
        print("can1 not found. Attempting to configure...")
        if not setup_can_interface('can1'):
            print("ERROR: Failed to configure can1!")
            print("Manual setup:")
            print("  sudo ip link set can1 type can bitrate 500000")
            print("  sudo ip link set can1 up")
            sys.exit(1)
    else:
        print("✓ can1 interface detected")
    
    print("\nInitializing CAN buses...")
    
    try:
        # can0 = CAR CAN bus, can1 = RADAR CAN bus
        can_bus1 = can.interface.Bus(interface='socketcan', channel='can0', bitrate=500000)
        can_bus2 = can.interface.Bus(interface='socketcan', channel='can1', bitrate=500000)
        print("✓ CAN buses initialized successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize CAN buses: {e}")
        sys.exit(1)
    
    try:
        # Try to load DBC file with strict=False to handle parsing errors
        db = cantools.database.load_file('opendbc/toyota_prius_2017_pt_generated.dbc', strict=False)
        print("✓ DBC file loaded (non-strict mode)")
    except FileNotFoundError:
        print("ERROR: DBC file not found!")
        print("Run: git submodule update --init")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to load DBC file: {e}")
        print("\nTrying alternative DBC file...")
        try:
            # Try the ADAS DBC as fallback
            db = cantools.database.load_file('opendbc/toyota_prius_2017_adas.dbc', strict=False)
            print("✓ Loaded alternative DBC file")
        except:
            print("ERROR: Could not load any DBC file. Exiting.")
            sys.exit(1)
    
    print("\n" + "=" * 60)
    print("Starting radar spoofing sequence...")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    # Setup notifier to listen for radar responses
    notifier = can.Notifier(can_bus2, [OnCan()], timeout=0.1)
    
    try:
        acc_message = db.get_message_by_name('ACC_CONTROL')
        frame = 0.
        
        # Send one-time initialization messages
        msg = db.get_message_by_name("SPEED")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({
                "ENCODER": 0,
                "SPEED": 1.44,
                "CHECKSUM": 0
            }),
            is_extended_id=False
        ))
        
        cruise_message = db.get_message_by_name('PCM_CRUISE')
        active_message = cruise_message.encode({
            "CRUISE_STATE": 9,
            "GAS_RELEASED": 0,
            "STANDSTILL_ON": 0,
            "ACCEL_NET": 0,
            "CHECKSUM": 0
        })
        msg = can.Message(arbitration_id=cruise_message.frame_id, data=active_message, is_extended_id=False)
        can_bus1.send(msg)
        
        msg = db.get_message_by_name("PCM_CRUISE_2")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({
                "MAIN_ON": 0,
                "LOW_SPEED_LOCKOUT": 0,
                "SET_SPEED": 0,
                "CHECKSUM": 0
            }),
            is_extended_id=False
        ))
        
        msg = db.get_message_by_name("ACC_CONTROL")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({
                "ACCEL_CMD": 0,
                "SET_ME_X63": 0,
                "RELEASE_STANDSTILL": 0,
                "SET_ME_1": 0,
                "CANCEL_REQ": 0,
                "CHECKSUM": 0
            }),
            is_extended_id=False
        ))
        
        msg = db.get_message_by_name("PCM_CRUISE_SM")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({
                "MAIN_ON": 0,
                "CRUISE_CONTROL_STATE": 0,
                "UI_SET_SPEED": 0
            }),
            is_extended_id=False
        ))
        
        print("Initialization messages sent. Entering main loop...\n")
        
        # Main loop - send periodic messages to keep radar alive
        while True:
            # Send ACC control message every frame
            if frame % 1 == 0:
                acc_msg = acc_message.encode({
                    "ACCEL_CMD": 0.0,
                    "SET_ME_X63": 0x63,
                    "SET_ME_1": 1,
                    "RELEASE_STANDSTILL": 1,
                    "CANCEL_REQ": 0,
                    "CHECKSUM": 113
                })
                msg = can.Message(arbitration_id=acc_message.frame_id, data=acc_msg, is_extended_id=False)
                can_bus1.send(msg)
            
            # Send static DSU messages at their specified intervals
            for (addr, ecu, cars, bus, fr_step, vl) in STATIC_MSGS:
                if frame % fr_step == 0:
                    # Handle special counter logic for 0x489 and 0x48a
                    tosend = bytearray(vl)
                    if addr in (0x489, 0x48a) and bus == 0:
                        cnt = int((frame / 100) % 0xf) + 1
                        if addr == 0x48a:
                            cnt += 1 << 7
                        tosend.append(cnt)
                    
                    # Select correct bus
                    can_bus = can_bus1 if bus == 0 else can_bus2
                    
                    message = can.Message(arbitration_id=addr, data=bytes(tosend), is_extended_id=False)
                    can_bus.send(message)
            
            frame += 1.
            time.sleep(1. / 100)  # 100 Hz update rate
    
    except KeyboardInterrupt:
        print("\n\nStopping radar control...")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nCleaning up...")
        try:
            notifier.stop()
        except:
            pass
        try:
            can_bus1.shutdown()
        except:
            pass
        try:
            can_bus2.shutdown()
        except:
            pass
        print("CAN buses shut down. Goodbye!")