#!/usr/bin/python3

import cantools
import can
import time
import sys
import os

"""
2019 Prius Radar Control - Enhanced for newer generation TSS 2.0
The 2019+ Prius has TSS 2.0 (Toyota Safety Sense 2.0) which may have different requirements
"""

class MessageLogger:
    def __init__(self):
        self.can0_tx = 0
        self.can1_rx = 0
        self.radar_status_msgs = 0
        self.radar_track_msgs = 0
        self.valid_tracks = 0
        self.last_4ff_data = None

logger = MessageLogger()

class OnCanRadar(can.Listener):
    def __init__(self):
        try:
            self.db = cantools.database.load_file('opendbc/toyota_prius_2017_adas.dbc', strict=False)
        except:
            self.db = None

    def on_message_received(self, msg):
        logger.can1_rx += 1
        
        if msg.arbitration_id == 0x4FF:
            logger.radar_status_msgs += 1
            # Track if the status changes
            if logger.last_4ff_data != msg.data.hex():
                logger.last_4ff_data = msg.data.hex()
                print(f"[can1 RX] 0x4FF STATUS (NEW): {msg.data.hex().upper()}")
        
        elif 0x210 <= msg.arbitration_id <= 0x21F:
            logger.radar_track_msgs += 1
            print(f"[can1 RX] 0x{msg.arbitration_id:03X} *** TRACK ***: {msg.data.hex().upper()}")
            
            if self.db:
                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                    if decoded.get("VALID") == 1:
                        logger.valid_tracks += 1
                        dist = decoded.get('LONG_DIST', 'N/A')
                        print(f"         🎯 VALID TRACK - Distance: {dist} m")
                except:
                    pass
        else:
            # Print any other unexpected messages
            print(f"[can1 RX] 0x{msg.arbitration_id:03X}: {msg.data.hex().upper()}")


# TSS 2.0 messages for 2019+ Prius (more aggressive activation sequence)
STATIC_MSGS_2019 = [
    # Critical DSU messages
    (0x141, 0, 2, b'\x00\x00\x00\x46'),      # DSU basic
    (0x128, 1, 3, b'\xf4\x01\x90\x83\x00\x37'),  # DSU control
    (0x283, 0, 3, b'\x00\x00\x00\x00\x00\x00\x8c'),  # DSU presence
    (0x344, 0, 5, b'\x00\x00\x01\x00\x00\x00\x00\x50'),  # DSU misc
    (0x160, 1, 7, b'\x00\x00\x08\x12\x01\x31\x9c\x51'),  # DSU state
    (0x161, 1, 7, b'\x00\x1e\x00\x00\x00\x80\x07'),  # DSU info
    
    # TSS 2.0 specific messages (try both Prius and RAV4 variants)
    (0x365, 0, 20, b'\x00\x00\x00\x80\x03\x00\x08'),  # Prius variant
    (0x366, 0, 20, b'\x00\x00\x4d\x82\x40\x02\x00'),  # Prius variant
    
    # Heartbeat
    (0x4CB, 0, 100, b'\x0c\x00\x00\x00\x00\x00\x00\x00'),
    
    # Additional messages that may help with TSS 2.0
    (0x1D4, 0, 3, b'\x00\x00\x00\x00\x00\x00\x00\x00'),  # SPEED alternative
    (0x620, 0, 20, b'\x00\x00\x00\x00\x00\x00\x00\x00'), # Additional TSS 2.0
]


def send_message(bus, msg_id, data, desc=""):
    message = can.Message(arbitration_id=msg_id, data=data, is_extended_id=False)
    bus.send(message)
    logger.can0_tx += 1
    if logger.can0_tx <= 30:
        print(f"[can0 TX] 0x{msg_id:03X} {desc}")


if __name__ == '__main__':
    print("=" * 70)
    print("2019 Prius Radar Control - TSS 2.0 Version")
    print("=" * 70)
    print()
    
    if os.geteuid() != 0:
        print("ERROR: Must run as root")
        sys.exit(1)
    
    try:
        can_bus0 = can.interface.Bus(interface='socketcan', channel='can0', bitrate=500000)
        can_bus1 = can.interface.Bus(interface='socketcan', channel='can1', bitrate=500000)
        print("✓ CAN buses initialized")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    # Try to load different DBC files for 2019+ models
    db = None
    dbc_files = [
        'opendbc/toyota_prius_2017_pt_generated.dbc',
        'opendbc/toyota_nodsu_pt_generated.dbc',
        'opendbc/toyota_tss2_pt_generated.dbc',
    ]
    
    for dbc_file in dbc_files:
        try:
            db = cantools.database.load_file(dbc_file, strict=False)
            print(f"✓ Loaded DBC: {dbc_file}")
            break
        except:
            continue
    
    if not db:
        print("ERROR: Could not load any DBC file")
        sys.exit(1)
    
    listener = OnCanRadar()
    notifier = can.Notifier(can_bus1, [listener], timeout=0.1)
    
    print("\n" + "=" * 70)
    print("Starting 2019+ Prius TSS 2.0 initialization sequence")
    print("This may take 30-90 seconds for the radar to fully activate")
    print("=" * 70)
    print()
    
    try:
        # Get message definitions
        try:
            acc_message = db.get_message_by_name('ACC_CONTROL')
            speed_msg = db.get_message_by_name("SPEED")
            cruise_msg = db.get_message_by_name('PCM_CRUISE')
            cruise2_msg = db.get_message_by_name("PCM_CRUISE_2")
            cruise_sm_msg = db.get_message_by_name("PCM_CRUISE_SM")
        except:
            print("Warning: Some messages not found in DBC, using hardcoded values")
            # We'll use hardcoded IDs as fallback
            acc_message = None
        
        frame = 0
        last_status = time.time()
        startup_phase = True
        
        print("Phase 1: Initial startup sequence (0-10 seconds)\n")
        
        # Enhanced startup sequence for TSS 2.0
        if acc_message:
            # Send initial messages multiple times
            for i in range(3):
                send_message(can_bus0, speed_msg.frame_id,
                           speed_msg.encode({"ENCODER": 0, "SPEED": 0.0, "CHECKSUM": 0}),
                           "SPEED")
                time.sleep(0.02)
            
            for i in range(3):
                send_message(can_bus0, cruise_msg.frame_id,
                           cruise_msg.encode({
                               "CRUISE_STATE": 8,  # Try state 8 instead of 9
                               "GAS_RELEASED": 1,
                               "STANDSTILL_ON": 0,
                               "ACCEL_NET": 0,
                               "CHECKSUM": 0
                           }), "PCM_CRUISE")
                time.sleep(0.02)
            
            send_message(can_bus0, cruise2_msg.frame_id,
                       cruise2_msg.encode({
                           "MAIN_ON": 1,  # Try with MAIN_ON=1
                           "LOW_SPEED_LOCKOUT": 0,
                           "SET_SPEED": 25,  # Set a speed
                           "CHECKSUM": 0
                       }), "PCM_CRUISE_2")
            
            send_message(can_bus0, acc_message.frame_id,
                       acc_message.encode({
                           "ACCEL_CMD": 0,
                           "SET_ME_X63": 0x63,
                           "RELEASE_STANDSTILL": 1,
                           "SET_ME_1": 1,
                           "CANCEL_REQ": 0,
                           "CHECKSUM": 0
                       }), "ACC_CONTROL")
            
            send_message(can_bus0, cruise_sm_msg.frame_id,
                       cruise_sm_msg.encode({
                           "MAIN_ON": 1,
                           "CRUISE_CONTROL_STATE": 2,  # Active state
                           "UI_SET_SPEED": 25
                       }), "PCM_CRUISE_SM")
        
        print("\nPhase 2: Continuous operation\n")
        
        # Main loop
        while True:
            # Send ACC control every frame (100 Hz)
            if frame % 1 == 0 and acc_message:
                acc_msg = acc_message.encode({
                    "ACCEL_CMD": 0.0,
                    "SET_ME_X63": 0x63,
                    "SET_ME_1": 1,
                    "RELEASE_STANDSTILL": 1,
                    "CANCEL_REQ": 0,
                    "CHECKSUM": 113
                })
                can_bus0.send(can.Message(arbitration_id=acc_message.frame_id,
                                         data=acc_msg, is_extended_id=False))
                logger.can0_tx += 1
            
            # Send static messages
            for (addr, bus, fr_step, vl) in STATIC_MSGS_2019:
                if frame % fr_step == 0:
                    tosend = bytearray(vl)
                    target_bus = can_bus0 if bus == 0 else can_bus1
                    target_bus.send(can.Message(arbitration_id=addr, 
                                               data=bytes(tosend),
                                               is_extended_id=False))
                    if bus == 0:
                        logger.can0_tx += 1
            
            # Status every 10 seconds
            now = time.time()
            if now - last_status >= 10.0:
                elapsed = int(now - last_status)
                if startup_phase and elapsed > 30:
                    startup_phase = False
                
                print(f"\n{'='*70}")
                print(f"STATUS - Running for {int(frame/100)} seconds")
                print(f"{'='*70}")
                print(f"Messages sent (can0): {logger.can0_tx}")
                print(f"Messages received (can1): {logger.can1_rx}")
                print(f"Radar status (0x4FF): {logger.radar_status_msgs}")
                print(f"  Last 0x4FF data: {logger.last_4ff_data}")
                print(f"Radar tracks (0x210-0x21F): {logger.radar_track_msgs}")
                print(f"Valid tracks: {logger.valid_tracks}")
                
                if logger.radar_status_msgs > 0 and logger.radar_track_msgs == 0:
                    print(f"\n⏳ Radar is alive (0x4FF heartbeat detected)")
                    if startup_phase:
                        print(f"   Waiting for tracking to start... (keep running 60-90s)")
                    else:
                        print(f"   If no tracks after 90s, the radar may need:")
                        print(f"   1. Different DBC file for 2019+ model")
                        print(f"   2. Objects in front of it (point at wall 2-10m away)")
                        print(f"   3. Proper mounting/orientation")
                
                print(f"{'='*70}\n")
                last_status = now
            
            frame += 1
            time.sleep(1.0 / 100)
    
    except KeyboardInterrupt:
        print("\n\nStopped")
    finally:
        print(f"\nFinal: TX={logger.can0_tx}, RX={logger.can1_rx}, ")
        print(f"Status={logger.radar_status_msgs}, Tracks={logger.radar_track_msgs}")
        
        try:
            notifier.stop()
            can_bus0.shutdown()
            can_bus1.shutdown()
        except:
            pass
        print("Done!")
