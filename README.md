# MeetLite

MeetLite is a lightweight, multi-party desktop video conferencing application built from scratch using Python's standard `socket` module. It uses a custom length-prefixed JSON protocol over TCP for room signalling and an RTP-like custom binary header over UDP for real-time video and audio relay. Users can create a meeting protected by a 6-character code and 4-digit PIN, or join existing meetings across a LAN or the internet.

## Requirements

- **Python 3.10+** (Windows, macOS, or Linux)
- A webcam and microphone (optional; MeetLite gracefully falls back to avatars and silent mode if hardware is missing)

## Installation

Install the client dependencies:

```bash
pip install -r requirements.txt