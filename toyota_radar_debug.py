#!/usr/bin/python3

import cantools
import can
import time
import sys
import os

"""
DEBUG VERSION - Shows all CAN activity
Raspberry Pi version for Waveshare Dual CAN Hat
"""

class OnCan(can.Listener):
    def __init__(self):
        self.msg_count = 0
        self.valid_tracks = 0
        try:
            self.db = cantools.database.load_file('opendbc/toyota_prius_2017_adas.dbc', strict=False)
            print("✓ OnCan listener: DBC loaded")
        except FileNotFoundError:
            print("Warning: DBC file not found for listener")
            self.db = None
        except Exception as e:
            print(f"Warning: Could not load DBC file for listener: {e}")
            self.db = None

    def on_message_received(self, msg):
        self.msg_count += 1
        
        # Print ALL messages from radar bus (can1)
        print(f"[RX] ID: 0x{msg.arbitration_id:03X} Data: {msg.data.hex().upper()} ({len(msg.data)} bytes)")
        
        # Check if it's a radar track message
        if 0x210 <= msg.arbitration_id <= 0x21F:
            if self.db:
                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                    if decoded.get("VALID") == 1:
                        self.valid_tracks += 1
                        print(f"  *** VALID TRACK at dist: {decoded.get('LONG_DIST', 'N/A')} m ***")
                    else:
                        print(f"  (Track message, but VALID={decoded.get('VALID', 'N/A')})")
                except Exception as e:
                    print(f"  (Could not decode: {e})")
            else:
                print(f"  (Radar track message - no DBC to decode)")


class ECU:
    CAM = 0
    DSU = 1
    APGS = 2


class CAR:
    PRIUS = 0
    LEXUS_RXH = 1
    RAV4 = 2
    RAV4H = 3
    COROLLA = 4


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
    try:
        result = os.system(f'ip link show {interface} > /dev/null 2>&1')
        return result == 0
    except Exception:
        return False


if __name__ == '__main__':
    print("=" * 70)
    print("Toyota Radar Control - DEBUG VERSION")
    print("=" * 70)
    
    if os.geteuid() != 0:
        print("WARNING: Not running as root. CAN setup may fail.")
        print()
    
    if not check_can_interface('can0'):
        print("ERROR: can0 not found!")
        sys.exit(1)
    else:
        print("✓ can0 interface detected")
    
    if not check_can_interface('can1'):
        print("ERROR: can1 not found!")
        sys.exit(1)
    else:
        print("✓ can1 interface detected")
    
    print("\nInitializing CAN buses...")
    
    try:
        can_bus1 = can.interface.Bus(interface='socketcan', channel='can0', bitrate=500000)
        can_bus2 = can.interface.Bus(interface='socketcan', channel='can1', bitrate=500000)
        print("✓ CAN buses initialized")
        print(f"  can0 (car bus): {can_bus1}")
        print(f"  can1 (radar bus): {can_bus2}")
    except Exception as e:
        print(f"ERROR: Failed to initialize CAN buses: {e}")
        sys.exit(1)
    
    try:
        db = cantools.database.load_file('opendbc/toyota_prius_2017_pt_generated.dbc', strict=False)
        print("✓ DBC file loaded")
    except Exception as e:
        print(f"ERROR: Failed to load DBC file: {e}")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("Starting radar spoofing sequence...")
    print("This version shows ALL CAN traffic on the radar bus (can1)")
    print("Press Ctrl+C to stop")
    print("=" * 70 + "\n")
    
    # Setup notifier
    listener = OnCan()
    notifier = can.Notifier(can_bus2, [listener], timeout=0.1)
    
    try:
        acc_message = db.get_message_by_name('ACC_CONTROL')
        frame = 0
        tx_count = 0
        
        # Send one-time initialization messages
        print("Sending initialization messages...")
        
        msg = db.get_message_by_name("SPEED")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({"ENCODER": 0, "SPEED": 1.44, "CHECKSUM": 0}),
            is_extended_id=False
        ))
        print(f"  [TX can0] SPEED (0x{msg.frame_id:03X})")
        
        cruise_message = db.get_message_by_name('PCM_CRUISE')
        active_message = cruise_message.encode({
            "CRUISE_STATE": 9, "GAS_RELEASED": 0, "STANDSTILL_ON": 0,
            "ACCEL_NET": 0, "CHECKSUM": 0
        })
        can_bus1.send(can.Message(arbitration_id=cruise_message.frame_id, 
                                  data=active_message, is_extended_id=False))
        print(f"  [TX can0] PCM_CRUISE (0x{cruise_message.frame_id:03X})")
        
        msg = db.get_message_by_name("PCM_CRUISE_2")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({"MAIN_ON": 0, "LOW_SPEED_LOCKOUT": 0, "SET_SPEED": 0, "CHECKSUM": 0}),
            is_extended_id=False
        ))
        print(f"  [TX can0] PCM_CRUISE_2 (0x{msg.frame_id:03X})")
        
        msg = db.get_message_by_name("ACC_CONTROL")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({"ACCEL_CMD": 0, "SET_ME_X63": 0, "RELEASE_STANDSTILL": 0,
                           "SET_ME_1": 0, "CANCEL_REQ": 0, "CHECKSUM": 0}),
            is_extended_id=False
        ))
        print(f"  [TX can0] ACC_CONTROL (0x{msg.frame_id:03X})")
        
        msg = db.get_message_by_name("PCM_CRUISE_SM")
        can_bus1.send(can.Message(
            arbitration_id=msg.frame_id,
            data=msg.encode({"MAIN_ON": 0, "CRUISE_CONTROL_STATE": 0, "UI_SET_SPEED": 0}),
            is_extended_id=False
        ))
        print(f"  [TX can0] PCM_CRUISE_SM (0x{msg.frame_id:03X})")
        
        print("\n" + "=" * 70)
        print("Initialization complete. Entering main loop...")
        print("Watching for messages on can1 (radar bus)...")
        print("=" * 70 + "\n")
        
        last_status = time.time()
        
        # Main loop
        while True:
            # Send ACC control message every frame
            if frame % 1 == 0:
                acc_msg = acc_message.encode({
                    "ACCEL_CMD": 0.0, "SET_ME_X63": 0x63, "SET_ME_1": 1,
                    "RELEASE_STANDSTILL": 1, "CANCEL_REQ": 0, "CHECKSUM": 113
                })
                msg = can.Message(arbitration_id=acc_message.frame_id, 
                                data=acc_msg, is_extended_id=False)
                can_bus1.send(msg)
                tx_count += 1
            
            # Send static DSU messages
            for (addr, ecu, cars, bus, fr_step, vl) in STATIC_MSGS:
                if frame % fr_step == 0:
                    tosend = bytearray(vl)
                    if addr in (0x489, 0x48a) and bus == 0:
                        cnt = int((frame / 100) % 0xf) + 1
                        if addr == 0x48a:
                            cnt += 1 << 7
                        tosend.append(cnt)
                    
                    can_bus = can_bus1 if bus == 0 else can_bus2
                    message = can.Message(arbitration_id=addr, data=bytes(tosend), 
                                        is_extended_id=False)
                    can_bus.send(message)
                    tx_count += 1
            
            # Print status every 5 seconds
            if time.time() - last_status >= 5.0:
                print(f"\n--- STATUS (frame {int(frame)}) ---")
                print(f"TX messages sent: {tx_count}")
                print(f"RX messages received: {listener.msg_count}")
                print(f"Valid tracks detected: {listener.valid_tracks}")
                print("---\n")
                last_status = time.time()
            
            frame += 1.0
            time.sleep(1.0 / 100)  # 100 Hz
    
    except KeyboardInterrupt:
        print("\n\nStopping radar control...")
        print(f"\nFinal Statistics:")
        print(f"  TX messages sent: {tx_count}")
        print(f"  RX messages received: {listener.msg_count}")
        print(f"  Valid tracks detected: {listener.valid_tracks}")
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
        print("Done!")
