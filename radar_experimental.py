#!/usr/bin/python3

import cantools
import can
import time
import sys
import os

"""
EXPERIMENTAL - Tries multiple activation strategies for 2019 Prius radar
The 0x4FF status of 3f00000200000000 suggests the radar is waiting for something specific
"""

class MessageLogger:
    def __init__(self):
        self.can0_tx = 0
        self.can1_tx = 0
        self.can1_rx = 0
        self.status_4ff_count = 0
        self.status_4ff_data = None
        self.other_messages = set()

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
            logger.status_4ff_count += 1
            new_data = msg.data.hex()
            if logger.status_4ff_data != new_data:
                print(f"[can1 RX] 0x4FF STATUS CHANGED: {new_data.upper()}")
                logger.status_4ff_data = new_data
        
        elif 0x210 <= msg.arbitration_id <= 0x21F:
            print(f"[can1 RX] 0x{msg.arbitration_id:03X} *** RADAR TRACK ***: {msg.data.hex().upper()}")
        
        else:
            # Track all other message IDs
            if msg.arbitration_id not in logger.other_messages:
                logger.other_messages.add(msg.arbitration_id)
                print(f"[can1 RX] 0x{msg.arbitration_id:03X} (NEW): {msg.data.hex().upper()}")


def try_strategy_1(can0, can1, db):
    """Original strategy - DSU messages on car bus only"""
    print("\n=== STRATEGY 1: Standard DSU spoof (car bus only) ===\n")
    
    messages = [
        (0x141, b'\x00\x00\x00\x46'),
        (0x128, b'\xf4\x01\x90\x83\x00\x37'),
        (0x283, b'\x00\x00\x00\x00\x00\x00\x8c'),
        (0x344, b'\x00\x00\x01\x00\x00\x00\x00\x50'),
        (0x160, b'\x00\x00\x08\x12\x01\x31\x9c\x51'),
        (0x161, b'\x00\x1e\x00\x00\x00\x80\x07'),
    ]
    
    for msg_id, data in messages:
        can0.send(can.Message(arbitration_id=msg_id, data=data, is_extended_id=False))
        logger.can0_tx += 1
        print(f"  TX can0: 0x{msg_id:03X}")
        time.sleep(0.05)


def try_strategy_2(can0, can1, db):
    """Try sending commands directly to radar on can1"""
    print("\n=== STRATEGY 2: Direct radar commands (radar bus) ===\n")
    
    # Some radars need commands sent directly to them
    radar_commands = [
        (0x750, b'\x02\x10\x03\x00\x00\x00\x00\x00'),  # Diagnostic session
        (0x750, b'\x02\x3E\x00\x00\x00\x00\x00\x00'),  # Tester present
        (0x750, b'\x02\x31\x01\x00\x00\x00\x00\x00'),  # Start routine
    ]
    
    for msg_id, data in radar_commands:
        can1.send(can.Message(arbitration_id=msg_id, data=data, is_extended_id=False))
        logger.can1_tx += 1
        print(f"  TX can1: 0x{msg_id:03X}")
        time.sleep(0.1)


def try_strategy_3(can0, can1, db):
    """Try aggressive ACC/cruise activation"""
    print("\n=== STRATEGY 3: Aggressive cruise control activation ===\n")
    
    try:
        # Try to strongly signal that cruise control is ACTIVE
        cruise = db.get_message_by_name('PCM_CRUISE')
        cruise2 = db.get_message_by_name('PCM_CRUISE_2')
        acc = db.get_message_by_name('ACC_CONTROL')
        
        # Send multiple times with "active" state
        for i in range(10):
            can0.send(can.Message(
                arbitration_id=cruise.frame_id,
                data=cruise.encode({
                    "CRUISE_STATE": 8,  # Active cruise
                    "GAS_RELEASED": 1,
                    "STANDSTILL_ON": 0,
                    "ACCEL_NET": 1,  # Accelerating
                    "CHECKSUM": 0
                }),
                is_extended_id=False
            ))
            logger.can0_tx += 1
            time.sleep(0.02)
        
        can0.send(can.Message(
            arbitration_id=cruise2.frame_id,
            data=cruise2.encode({
                "MAIN_ON": 1,
                "LOW_SPEED_LOCKOUT": 0,
                "SET_SPEED": 50,  # 50 mph
                "CHECKSUM": 0
            }),
            is_extended_id=False
        ))
        logger.can0_tx += 1
        
        can0.send(can.Message(
            arbitration_id=acc.frame_id,
            data=acc.encode({
                "ACCEL_CMD": 1.0,  # Small acceleration
                "SET_ME_X63": 0x63,
                "SET_ME_1": 1,
                "RELEASE_STANDSTILL": 1,
                "CANCEL_REQ": 0,
                "CHECKSUM": 113
            }),
            is_extended_id=False
        ))
        logger.can0_tx += 1
        
        print("  Sent aggressive cruise activation")
    except Exception as e:
        print(f"  Error: {e}")


def try_strategy_4(can0, can1, db):
    """Try TSS 2.0 specific messages"""
    print("\n=== STRATEGY 4: TSS 2.0 specific commands ===\n")
    
    # TSS 2.0 might need these additional messages
    tss2_messages = [
        (0x224, b'\x00\x00\x00\x00\x00\x00\x00\x00'),  # Steering angle
        (0x1D4, b'\x00\x00\x00\x00\x00\x00\x00\x00'),  # Additional speed
        (0x620, b'\x01\x00\x00\x00\x00\x00\x00\x00'),  # TSS 2.0 enable
        (0x614, b'\x00\x00\x00\x00\x00\x00\x00\x00'),  # Additional control
    ]
    
    for msg_id, data in tss2_messages:
        can0.send(can.Message(arbitration_id=msg_id, data=data, is_extended_id=False))
        logger.can0_tx += 1
        print(f"  TX can0: 0x{msg_id:03X}")
        time.sleep(0.05)


def decode_4ff_status(data_hex):
    """Try to decode what the 0x4FF status means"""
    data = bytes.fromhex(data_hex)
    print(f"\n0x4FF Status Analysis: {data_hex.upper()}")
    print(f"  Byte 0 (0x{data[0]:02X}): ", end="")
    
    byte0 = data[0]
    if byte0 == 0x3F:
        print("0x3F = possibly 'standby' or 'ready' state")
    elif byte0 == 0x00:
        print("0x00 = off/disabled")
    elif byte0 & 0x80:
        print("High bit set - active/tracking?")
    else:
        print(f"Unknown state")
    
    print(f"  Byte 3 (0x{data[3]:02X}): ", end="")
    if data[3] == 0x02:
        print("0x02 = might indicate 'waiting for activation'")
    elif data[3] == 0x00:
        print("0x00 = inactive")
    else:
        print(f"Unknown")


if __name__ == '__main__':
    print("=" * 70)
    print("EXPERIMENTAL 2019 Prius Radar Activation")
    print("Trying multiple strategies to activate tracking mode")
    print("=" * 70)
    print()
    
    if os.geteuid() != 0:
        print("ERROR: Must run as root")
        sys.exit(1)
    
    try:
        can0 = can.interface.Bus(interface='socketcan', channel='can0', bitrate=500000)
        can1 = can.interface.Bus(interface='socketcan', channel='can1', bitrate=500000)
        print("✓ CAN buses ready\n")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    try:
        db = cantools.database.load_file('opendbc/toyota_prius_2017_pt_generated.dbc', strict=False)
    except:
        print("Warning: Could not load DBC file")
        db = None
    
    listener = OnCanRadar()
    notifier = can.Notifier(can1, [listener], timeout=0.1)
    
    print("Starting systematic activation attempts...")
    print("=" * 70)
    
    try:
        # Try each strategy with a 20 second test period
        strategies = [
            try_strategy_1,
            try_strategy_2, 
            try_strategy_3,
            try_strategy_4
        ]
        
        for i, strategy in enumerate(strategies, 1):
            print(f"\n{'='*70}")
            print(f"Testing Strategy {i}/4")
            print(f"{'='*70}")
            
            strategy(can0, can1, db)
            
            # Wait and observe
            print(f"\nWaiting 20 seconds to observe results...\n")
            start = time.time()
            while time.time() - start < 20:
                # Send basic keepalive
                if db:
                    try:
                        acc = db.get_message_by_name('ACC_CONTROL')
                        can0.send(can.Message(
                            arbitration_id=acc.frame_id,
                            data=acc.encode({
                                "ACCEL_CMD": 0.0,
                                "SET_ME_X63": 0x63,
                                "SET_ME_1": 1,
                                "RELEASE_STANDSTILL": 1,
                                "CANCEL_REQ": 0,
                                "CHECKSUM": 113
                            }),
                            is_extended_id=False
                        ))
                        logger.can0_tx += 1
                    except:
                        pass
                
                time.sleep(0.1)
            
            # Show results
            print(f"\nStrategy {i} Results:")
            print(f"  Messages sent: can0={logger.can0_tx}, can1={logger.can1_tx}")
            print(f"  Messages received: {logger.can1_rx}")
            print(f"  0x4FF status: {logger.status_4ff_count} (data: {logger.status_4ff_data})")
            if logger.other_messages:
                print(f"  Other message IDs seen: {[hex(x) for x in sorted(logger.other_messages)]}")
            
            if logger.status_4ff_data:
                decode_4ff_status(logger.status_4ff_data)
        
        # Final continuous attempt
        print(f"\n{'='*70}")
        print("FINAL ATTEMPT: Continuous operation with all strategies combined")
        print("Running for 60 seconds... (Press Ctrl+C to stop early)")
        print(f"{'='*70}\n")
        
        start = time.time()
        frame = 0
        while time.time() - start < 60:
            # Rotate through strategies
            if frame % 500 == 0:  # Every 5 seconds
                strategy_num = (frame // 500) % 4
                strategies[strategy_num](can0, can1, db)
            
            # Continuous keepalive
            if db and frame % 10 == 0:
                try:
                    acc = db.get_message_by_name('ACC_CONTROL')
                    can0.send(can.Message(
                        arbitration_id=acc.frame_id,
                        data=acc.encode({
                            "ACCEL_CMD": 0.0,
                            "SET_ME_X63": 0x63,
                            "SET_ME_1": 1,
                            "RELEASE_STANDSTILL": 1,
                            "CANCEL_REQ": 0,
                            "CHECKSUM": 113
                        }),
                        is_extended_id=False
                    ))
                    logger.can0_tx += 1
                except:
                    pass
            
            frame += 1
            time.sleep(0.01)
        
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        print(f"\n{'='*70}")
        print("FINAL RESULTS")
        print(f"{'='*70}")
        print(f"Total TX: can0={logger.can0_tx}, can1={logger.can1_tx}")
        print(f"Total RX: {logger.can1_rx}")
        print(f"0x4FF status messages: {logger.status_4ff_count}")
        print(f"Final 0x4FF data: {logger.status_4ff_data}")
        
        if logger.status_4ff_data:
            decode_4ff_status(logger.status_4ff_data)
        
        if logger.other_messages:
            print(f"\nAll message IDs seen on can1:")
            for msg_id in sorted(logger.other_messages):
                print(f"  0x{msg_id:03X}")
        
        print(f"\n{'='*70}")
        print("CONCLUSION:")
        if logger.can1_rx > 0 and not any(0x210 <= x <= 0x21F for x in logger.other_messages):
            print("✓ Radar is responding (0x4FF heartbeat)")
            print("✗ Radar NOT entering tracking mode (no 0x210-0x21F messages)")
            print("\nPossible causes:")
            print("  1. 2019 Prius radar needs firmware/hardware enablement")
            print("  2. Radar needs calibration procedure first")
            print("  3. Different radar model (Continental vs Denso)")
            print("  4. Radar is in diagnostic/service mode")
            print("\nNext steps:")
            print("  - Check radar part number on physical unit")
            print("  - Look for 'Denso' or 'Continental' marking")
            print("  - Try scanning OBD codes: candump can0")
        
        try:
            notifier.stop()
            can0.shutdown()
            can1.shutdown()
        except:
            pass
        
        print("=" * 70)
