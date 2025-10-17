#!/usr/bin/env python3
"""
Terminal visualization for Toyota radar tracks using the reusable radar driver.
"""

import argparse
import curses
import time
from typing import Dict

from toyota_radar_driver import (
    RadarTrack,
    ToyotaRadarConfig,
    ToyotaRadarDriver,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize Toyota radar tracks with a curses UI."
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
        "--track-timeout",
        type=float,
        default=0.5,
        help="Seconds before removing stale tracks.",
    )
    parser.add_argument(
        "--keepalive-rate-hz",
        type=float,
        default=100.0,
        help="Frequency for radar keep-alive loop.",
    )
    parser.add_argument(
        "--notifier-timeout",
        type=float,
        default=0.1,
        help="python-can notifier timeout in seconds.",
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
        help="Disable internal keep-alive loop (another node must provide it).",
    )
    parser.add_argument(
        "--max-long",
        type=float,
        default=60.0,
        help="Max longitudinal distance in meters shown.",
    )
    parser.add_argument(
        "--max-lat",
        type=float,
        default=8.0,
        help="Max lateral distance (abs) in meters shown.",
    )
    parser.add_argument(
        "--refresh-hz",
        type=float,
        default=10.0,
        help="Screen refresh rate in Hz.",
    )
    return parser.parse_args()


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def draw_grid(
    screen,
    top: int,
    left: int,
    width: int,
    height: int,
    origin_x: int,
    origin_y: int,
) -> None:
    bottom = top + height - 1
    right = left + width - 1

    for x in range(left, right + 1):
        screen.addch(top, x, "-")
        screen.addch(bottom, x, "-")
    for y in range(top, bottom + 1):
        screen.addch(y, left, "|")
        screen.addch(y, right, "|")

    for x in range(left + 1, right):
        screen.addch(origin_y, x, "-")
    for y in range(top + 1, bottom):
        screen.addch(y, origin_x, "|")
    screen.addch(origin_y, origin_x, "+")


def draw_tracks(
    screen,
    tracks: Dict[int, RadarTrack],
    *,
    grid_top: int,
    grid_bottom: int,
    grid_left: int,
    grid_right: int,
    grid_width: int,
    grid_height: int,
    origin_x: int,
    origin_y: int,
    max_long: float,
    max_lat: float,
    color_pair: int,
) -> None:
    for track in tracks.values():
        long_ratio = clamp(track.long_dist / max_long, 0.0, 1.0)
        lat_ratio = clamp(track.lat_dist / max_lat, -1.0, 1.0)

        rel_y = max(1, int(round(long_ratio * (grid_height - 3))))
        rel_x = int(round(lat_ratio * ((grid_width - 3) / 2)))

        y = origin_y - rel_y
        x = origin_x + rel_x

        if grid_top + 1 <= y <= grid_bottom - 1 and grid_left + 1 <= x <= grid_right - 1:
            marker = format(track.track_id, "X")[-1]
            if track.new_track:
                marker = marker.lower()
            if color_pair:
                screen.addch(y, x, marker, curses.color_pair(color_pair))
            else:
                screen.addch(y, x, marker)


def draw_info_panel(
    screen,
    tracks: Dict[int, RadarTrack],
    *,
    panel_x: int,
    panel_width: int,
    max_rows: int,
    now: float,
) -> None:
    if panel_width <= 0:
        return

    header = "Track  Long(m)  Lat(m)  RelSpd(m/s)  Age(ms)"
    screen.addnstr(2, panel_x, header, panel_width - 1)

    ordered = sorted(tracks.values(), key=lambda t: t.long_dist)
    for idx, track in enumerate(ordered[: max_rows - 3]):
        age_ms = (now - track.timestamp) * 1000.0
        line = f"{track.track_id:>5X}  {track.long_dist:>7.2f}  {track.lat_dist:>6.2f}  {track.rel_speed:>11.2f}  {age_ms:>7.0f}"
        screen.addnstr(3 + idx, panel_x, line, panel_width - 1)


def run_curses(stdscr, driver: ToyotaRadarDriver, args: argparse.Namespace) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(0)

    color_pair = 0
    if curses.has_colors():
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        color_pair = 1

    refresh_delay = 1.0 / max(args.refresh_hz, 1.0)

    while True:
        loop_start = time.time()

        tracks = driver.get_tracks()
        now = time.time()

        stdscr.erase()
        height, width = stdscr.getmaxyx()

        if width >= 80:
            panel_width = min(max(28, int(width * 0.35)), width - 40)
        elif width >= 60:
            panel_width = 24
        else:
            panel_width = 0

        if panel_width > 0:
            panel_x = width - panel_width
            grid_width = max(20, width - panel_width - 2)
        else:
            panel_x = width
            grid_width = max(20, width - 2)

        grid_height = max(10, height - 4)
        grid_top = 2
        grid_left = 1
        grid_bottom = grid_top + grid_height - 1
        grid_right = grid_left + grid_width - 1
        origin_x = grid_left + grid_width // 2
        origin_y = grid_top + grid_height - 2

        stdscr.addnstr(0, 1, "Toyota Radar Tracks (press 'q' to quit)", width - 2)

        status_parts = [
            f"Tracks: {len(tracks):2d}",
            f"Range +/-{args.max_lat:.1f}m x {args.max_long:.1f}m",
            f"Refresh: {args.refresh_hz:.1f}Hz",
            f"RX: {driver.message_count():d}",
        ]
        keepalive = driver.keepalive_status()
        if keepalive:
            status_parts.append(f"KA TX: {int(keepalive['tx_count']):d}")
            if keepalive["last_error"]:
                status_parts.append(f"ERR: {keepalive['last_error']}")
        status_line = "  ".join(status_parts)
        stdscr.addnstr(1, 1, status_line, width - 2)

        draw_grid(stdscr, grid_top, grid_left, grid_width, grid_height, origin_x, origin_y)
        draw_tracks(
            stdscr,
            tracks,
            grid_top=grid_top,
            grid_bottom=grid_bottom,
            grid_left=grid_left,
            grid_right=grid_right,
            grid_width=grid_width,
            grid_height=grid_height,
            origin_x=origin_x,
            origin_y=origin_y,
            max_long=args.max_long,
            max_lat=args.max_lat,
            color_pair=color_pair,
        )
        draw_info_panel(
            stdscr,
            tracks,
            panel_x=panel_x,
            panel_width=panel_width,
            max_rows=height,
            now=now,
        )

        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            break

        elapsed = time.time() - loop_start
        if elapsed < refresh_delay:
            time.sleep(refresh_delay - elapsed)


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

    try:
        driver.start()
    except Exception as exc:
        driver.stop()
        raise SystemExit(f"Failed to start radar driver: {exc}")

    try:
        curses.wrapper(run_curses, driver, args)
    except KeyboardInterrupt:
        pass
    finally:
        driver.stop()


if __name__ == "__main__":
    main()
