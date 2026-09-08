
# Raspberry Pi Seamless TV Channel Kiosk

A high-performance, hardware-accelerated digital signage kiosk built for the Raspberry Pi. It simulates a retro TV tuner, seamlessly switching between local video channels synchronized to a master clock using a physical IR remote control.

Unlike standard media players, this system utilizes **Direct Memory Access (DMA)** hardware sampling to read non-standard or dirty IR signals directly into RAM without relying on standard OS kernel IR decoders or heavy CPU polling.

---

## Key Features

* **Atomic Video Switching:** Zero-delay channel changes using native `python-mpv` C-bindings.
* **Synchronized Continuous Playback:** Videos play relative to a global program start time. Switching back to a channel jumps to the exact timestamp as if the stream was running continuously in the background.
* **Hardware-Accelerated DMA Decoding:** Uses `pigpio` to sample GPIO light pulses every few microseconds, completely bypassing CPU scheduling locks and video player load spikes.
* **Channel Navigation:** Supports direct numeric hotkeys (0–9) and relative Channel UP / Channel DOWN stepping via a state machine.
* **Kiosk Ready:** Configured to automatically launch in fullscreen mode upon system boot.

---

## Hardware Requirements

* **Raspberry Pi** (Pi 4 or Pi 5 recommended running Raspberry Pi OS Bookworm)
* **TSOP38238** (or similar 38kHz) IR Receiver Module
* **IR Remote Control** (e.g., SeKi Easy / Universal IR Remote)
* MicroSD Card & HDMI Display

### Pin Wiring (GPIO)

| IR Receiver Pin | Raspberry Pi Pin |
| :--- | :--- |
| **OUT (Signal)** | GPIO 17 (Physical Pin 11) |
| **GND** | Ground (Physical Pin 6 or 9) |
| **VCC** | 3.3V (Physical Pin 1) |

---

## Prerequisites & Installation

### 1. Install System Dependencies & `mpv`

```bash
sudo apt update
sudo apt install -y python3-pip python3-mpv mpv build-essential unzip

```

### 2. Compile `pigpio` from Source (Debian 12 Bookworm Fix)

Debian Bookworm removes `pigpio` from standard `apt` repositories. Compile the daemon from source to enable DMA memory sampling:

```bash
# Download and extract pigpio source
wget [https://github.com/joan2937/pigpio/archive/master.zip](https://github.com/joan2937/pigpio/archive/master.zip)
unzip master.zip
cd pigpio-master

# Compile and install
make
sudo make install

# Install Python bindings
sudo apt install -y python3-pigpio

```

---

## Configuration & Usage

### 1. Map Video Files

Place your MP4 media files in `/home/raspart/Videos/` (or update the file paths inside `video_player.py`).

Update the `VIDEO_MAP` dictionary inside `video_player.py` with your hex codes and file paths:

```python
VIDEO_MAP = {
    "0x977": "/home/raspart/Videos/Channel_1_CCTV.mp4",        
    "0x975": "/home/raspart/Videos/Channel_2_Mushroom.mp4", 
    # Add remaining channels...
}

```

### 2. Configure Navigation Hotkeys

Update `BTN_UP` and `BTN_DOWN` at the top of `video_player.py` with your remote's hex values:

```python
BTN_UP = "0xYOUR_UP_HEX_CODE"
BTN_DOWN = "0xYOUR_DOWN_HEX_CODE"

```

### 3. Running Manually

Ensure the `pigpiod` daemon is running before starting the player:

```bash
# Start DMA daemon
sudo pigpiod

# Run the player
python3 video_player.py

```

---

## Auto-Start Setup (Kiosk Mode)

To make the Raspberry Pi boot directly into the TV channel player upon power-on:

### Step 1: Create `pigpiod` System Service

Create `/etc/systemd/system/pigpiod.service`:

```ini
[Unit]
Description=Pigpio hardware daemon
After=network.target

[Service]
ExecStart=/usr/local/bin/pigpiod -l
Type=forking
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target

```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

```

### Step 2: Configure Desktop Autostart

Create `/home/raspart/.config/autostart/tv_channel.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=TV Channel Player
Exec=bash -c "sleep 10 && /usr/bin/python3 /home/raspart/video_player.py"
Terminal=true

```

---

## Architecture Overview

```text
  [ IR Remote ] 
       │ (IR Light Pulses)
       ▼
 [ TSOP38238 ] ──► GPIO 17 ──► [ pigpiod C-Daemon ] (DMA Hardware Sampling)
                                       │
                                       ▼ (Microsecond Timings)
                              [ IRDecoder Class ] (Agnostic Gap Analysis)
                                       │
                                       ▼ (Queue)
                             [ video_player.py ] (State Machine & Synchronization)
                                       │
                                       ▼
                             [ mpv Media Engine ] (C-API Atomic Seeking)

```

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
