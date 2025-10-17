#!/usr/bin/env python3
"""
Example script showing how to consume Toyota radar tracks via callbacks.
"""

import argparse
import time
from typing import Dict

from toyota_radar_driver import RadarTrack, ToyotaRadarConfig, ToyotaRadarDriver


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log Toyota radar tracks using the modular radar driver."
    )
    parser.add_argument("--radar-channel", default="can1", help="Radar CAN channel.")
    parser.add_argument("--car-channel", default="can0", help="Car CAN channel.")
    parser.add_argument(
        "--interface",
        default="socketcan",
        help="Default python-can interface for both channels.",
    )
    parser.add_argument(
        "--radar-interface",
        default=None,
        help="Override python-can interface for radar channel.",
    )
    parser.add_argument(
        "--car-interface",
        default=None,
        help="Override python-can interface for car channel.",
    )
    parser.add_argument("--bitrate", type=int, default=500000, help="CAN bitrate.")
    parser.add_argument(
        "--radar-dbc",
        default="opendbc/toyota_prius_2017_adas.dbc",
        help="DBC used to decode radar tracks.",
    )
    parser.add_argument(
        "--control-dbc",
        default="opendbc/toyota_prius_2017_pt_generated.dbc",
        help="DBC containing ACC/DSU keep-alive messages.",
    )
    parser.add_argument(
        "--no-setup",
        action="store_true",
        help="Skip bringing interfaces up with ip link.",
    )
    parser.add_argument(
        "--use-sudo",
        action="store_true",
        help="Run interface setup commands with sudo.",
    )
    parser.add_argument(
        "--setup-extra",
        action="append",
        default=[],
        metavar="TOKEN",
        help="Extra tokens to prefix ip link commands (repeatable).",
    )
    parser.add_argument(
        "--no-keepalive",
        action="store_true",
        help="Disable internal keep-alive loop.",
    )
    parser.add_argument(
        "--keepalive-rate-hz",
        type=float,
        default=100.0,
        help="Frequency for radar keep-alive loop.",
    )
    parser.add_argument(
        "--track-timeout",
        type=float,
        default=0.5,
        help="Seconds before removing stale tracks from the driver cache.",
    )
    parser.add_argument(
        "--notifier-timeout",
        type=float,
        default=0.1,
        help="python-can notifier timeout in seconds.",
    )
    parser.add_argument(
        "--print-interval",
        type=float,
        default=0.25,
        help="Minimum seconds between prints for the same track.",
    )
    parser.add_argument(
        "--summary-interval",
        type=float,
        default=5.0,
        help="Seconds between summary statistics prints.",
    )
    return parser.parse_args()


class TrackLogger:
    def __init__(self, min_interval: float) -> None:
        self._last_print: Dict[int, float] = {}
        self._min_interval = max(min_interval, 0.0)

    def __call__(self, track: RadarTrack) -> None:
        now = time.time()
        last = self._last_print.get(track.track_id, 0.0)
        if now - last >= self._min_interval:
            self._last_print[track.track_id] = now
            print(
                f"{time.strftime('%H:%M:%S')} track 0x{track.track_id:02X} "
                f"long={track.long_dist:5.2f}m lat={track.lat_dist:5.2f}m "
                f"rel_speed={track.rel_speed:5.2f}m/s new={track.new_track}"
            )


def main() -> None:
    args = parse_args()

    config = ToyotaRadarConfig(
        radar_channel=args.radar_channel,
        car_channel=args.car_channel,
        interface=args.interface,
        radar_interface=args.radar_interface,
        car_interface=args.car_interface,
        bitrate=args.bitrate,
        radar_dbc=args.radar_dbc,
        control_dbc=args.control_dbc,
        keepalive_rate_hz=args.keepalive_rate_hz,
        track_timeout=args.track_timeout,
        notifier_timeout=args.notifier_timeout,
        auto_setup=not args.no_setup,
        use_sudo=args.use_sudo,
        setup_extra_args=args.setup_extra,
        keepalive_enabled=not args.no_keepalive,
    )

    driver = ToyotaRadarDriver(config)
    driver.register_track_callback(TrackLogger(args.print_interval))

    try:
        driver.start()
    except Exception as exc:
        driver.stop()
        raise SystemExit(f"Failed to start radar driver: {exc}")

    print("Toyota radar driver started. Waiting for track callbacks (Ctrl+C to exit).")

    try:
        next_summary = time.time() + args.summary_interval
        while True:
            time.sleep(0.1)
            if time.time() >= next_summary:
                tracks = driver.get_tracks()
                count = len(tracks)
                status = driver.keepalive_status()
                parts = [f"Tracks cached: {count}", f"RX messages: {driver.message_count()}"]
                if status:
                    parts.append(f"KA TX: {int(status['tx_count'])}")
                    if status["last_error"]:
                        parts.append(f"ERR: {status['last_error']}")
                print(" | ".join(parts))
                next_summary = time.time() + args.summary_interval
    except KeyboardInterrupt:
        print("\nStopping driver...")
    finally:
        driver.stop()


if __name__ == "__main__":
    main()
