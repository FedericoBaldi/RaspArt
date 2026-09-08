import time
import mpv
import os
import pigpio
import queue
from mutagen.mp4 import MP4

# ==========================================
# 1. CONFIGURATION
# ==========================================
IR_PIN = 17  # BCM pin 17 (Physical pin 11)

# REPLACE THESE with the actual hex codes from your terminal
BTN_UP = "0x161ce"
BTN_DOWN = "0x161ce1ce3"

VIDEO_MAP = {
    "0x977": "/home/raspart/Videos/Channel_1_CCTV.mp4",        
    "0x975": "/home/raspart/Videos/Channel_2_Mushroom.mp4", 
    "0x97f": "/home/raspart/Videos/Channel_3_Cow.mp4",         
    "0x97b": "/home/raspart/Videos/Channel_4_Dup.mp4",         
    "0x97a": "/home/raspart/Videos/Channel_5_Kino.mp4",         
    "0x4":   "/home/raspart/Videos/Channel_6_Process.mp4",     
    "0x2f":  "/home/raspart/Videos/Channel_7_Televendita.mp4",         
    "0x7":   "/home/raspart/Videos/Channel_8_trasporto.mp4",   
    "0x1":   "/home/raspart/Videos/Channel_9_Credits.mp4",     
    "0x0":   "/home/raspart/Videos/Channel_0_Noise.mp4",       
}

# The logical flow of your channels (1 through 9, then 0)
ORDERED_CHANNELS = [
    "0x977",  # Ch 1
    "0x975",  # Ch 2
    "0x97f",  # Ch 3
    "0x97b",  # Ch 4
    "0x97a",  # Ch 5
    "0x4",    # Ch 6
    "0x2f",   # Ch 7
    "0x7",    # Ch 8
    "0x1",    # Ch 9
    "0x0",    # Ch 0
]

MANUAL_DURATIONS = {
    "0x1": 323.0,  
}

# ==========================================
# 2. AUTO-PROBE VIDEO DURATIONS
# ==========================================
def analyze_videos(mapping):
    print("Analyzing video files...")
    video_data = {}
    for hex_code, path in mapping.items():
        if os.path.exists(path):
            try:
                if hex_code in MANUAL_DURATIONS:
                    duration = MANUAL_DURATIONS[hex_code]
                    print(f" -> Found: {os.path.basename(path)} (MANUAL OVERRIDE: {duration:.2f}s)")
                else:
                    video_file = MP4(path)
                    duration = video_file.info.length
                    print(f" -> Found: {os.path.basename(path)} ({duration:.2f}s)")
                video_data[hex_code] = {"path": path, "duration": duration}
            except Exception as e:
                print(f" -> Error reading {path}: {e}")
        else:
            print(f" -> Warning: File not found at {path}")
    return video_data

# ==========================================
# 3. THE DMA HARDWARE DECODER (pigpio)
# ==========================================
class IRDecoder:
    def __init__(self, pi, pin, output_queue):
        self.pi = pi
        self.pin = pin
        self.queue = output_queue
        
        self.pi.set_mode(pin, pigpio.INPUT)
        self.pi.set_pull_up_down(pin, pigpio.PUD_UP)
        
        self.in_code = False
        self.last_tick = 0
        self.pulses = []
        self.cb = self.pi.callback(pin, pigpio.EITHER_EDGE, self._cbf)

    def _cbf(self, gpio, level, tick):
        if level == pigpio.TIMEOUT:
            self.pi.set_watchdog(self.pin, 0) 
            if len(self.pulses) > 10:
                self._decode()
            self.pulses = []
            self.in_code = False
            return

        if not self.in_code:
            if level == 0: 
                self.in_code = True
                self.last_tick = tick
                self.pi.set_watchdog(self.pin, 20) 
        else:
            diff_us = pigpio.tickDiff(self.last_tick, tick)
            self.last_tick = tick
            previous_state = 1 if level == 0 else 0
            self.pulses.append((previous_state, diff_us / 1000000.0))

    def _decode(self):
        binary_string = ""
        for state, duration in self.pulses:
            if state == 1: 
                if duration > 0.001:  
                    binary_string += "1"
                elif duration > 0.0002: 
                    binary_string += "0"

        if binary_string:
            try:
                hex_code = hex(int(binary_string, 2))
                self.queue.put(hex_code)
            except ValueError:
                pass

    def cancel(self):
        self.cb.cancel()

# ==========================================
# 4. MAIN LOOP & TV CHANNEL PLAYER
# ==========================================
def main():
    analyzed_videos = analyze_videos(VIDEO_MAP)
    
    if not analyzed_videos:
        print("\nNo valid videos found. Exiting...")
        return

    pi = pigpio.pi()
    if not pi.connected:
        print("\n[!] FATAL ERROR: pigpio daemon is not running!")
        print("Run 'sudo pigpiod' in a separate terminal and try again.")
        return

    ir_queue = queue.Queue()
    decoder = IRDecoder(pi, IR_PIN, ir_queue)

    PROGRAM_START_TIME = time.time()
    current_channel_index = 0  # Tracks our position in the ORDERED_CHANNELS list

    print("\nInitializing TV Channel player...")
    player = mpv.MPV(
        fullscreen=True, 
        idle=True, 
        force_window=True, 
        hwdec='auto',
        osc=False,
        cursor_autohide='always',
        loop_file='inf',
        profile='fast',
        cache='yes',
        demuxer_max_bytes='128M'
    )

    print(f"[*] DMA Hardware Decoder active on GPIO {IR_PIN}.")
    print("[*] Waiting for remote signals... (Press Ctrl+C to exit)\n")

    try:
        while True:
            if not ir_queue.empty():
                raw_code = ir_queue.get()
                code_to_play = raw_code
                
                # 1. Intercept Up/Down commands and calculate the new channel code
                if raw_code == BTN_UP:
                    current_channel_index = (current_channel_index + 1) % len(ORDERED_CHANNELS)
                    code_to_play = ORDERED_CHANNELS[current_channel_index]
                    print(" -> Action: Channel UP")
                elif raw_code == BTN_DOWN:
                    current_channel_index = (current_channel_index - 1) % len(ORDERED_CHANNELS)
                    code_to_play = ORDERED_CHANNELS[current_channel_index]
                    print(" -> Action: Channel DOWN")
                else:
                    print(f"Signal Detected: {raw_code}")

                # 2. Play the mapped channel
                if code_to_play in analyzed_videos:
                    # Sync the tracker so up/down works correctly after jumping directly to a number
                    if code_to_play in ORDERED_CHANNELS:
                        current_channel_index = ORDERED_CHANNELS.index(code_to_play)

                    vid_data = analyzed_videos[code_to_play]
                    video_path = vid_data["path"]
                    duration = vid_data["duration"]
                    
                    elapsed_time = time.time() - PROGRAM_START_TIME
                    seek_time = (elapsed_time % duration) if duration > 0 else 0
                    
                    print(f" -> Channel Switch: {os.path.basename(video_path)} (Jumping to {seek_time:.2f}s)")
                    
                    try:
                        # ATOMIC LOAD: Flawless hardware seeking
                        player.loadfile(video_path, mode='replace', start=str(seek_time))
                    except Exception as e:
                        print(f" -> Engine load error (ignoring): {e}")
                else:
                    print(" -> Unmapped button.")
                
                # Debounce to prevent rapid-fire clicking
                time.sleep(0.3)
                
                # Clear out any extra clicks that backed up in the queue
                while not ir_queue.empty():
                    ir_queue.get()
                    
            time.sleep(0.01)
                
    except KeyboardInterrupt:
        print("\n[*] Shutting down gracefully...")
    finally:
        player.terminate()
        decoder.cancel()
        pi.stop()

if __name__ == "__main__":
    main()