#!/usr/bin/env python3
"""
NES Emulator Main Entry Point
Optimized rendering + real audio output via pygame.mixer
"""

import sys
import time
import pygame
import numpy as np
from cartridge import Cartridge
from nes import NES

# Key mappings
KEY_MAP = {
    pygame.K_UP: 'UP',
    pygame.K_DOWN: 'DOWN',
    pygame.K_LEFT: 'LEFT',
    pygame.K_RIGHT: 'RIGHT',
    pygame.K_z: 'A',
    pygame.K_x: 'B',
    pygame.K_RETURN: 'START',
    pygame.K_RSHIFT: 'SELECT',
}

# Audio constants
SAMPLE_RATE = 44100
AUDIO_BUFFER_SIZE = 1024  # frames per chunk
NES_CPU_FREQ = 1789773  # NTSC CPU frequency


class AudioStreamer:
    """Ring-buffer backed audio streamer using pygame.mixer + Sound queue."""

    def __init__(self, apu):
        self.apu = apu
        self.sample_rate = SAMPLE_RATE
        self.cycles_per_sample = NES_CPU_FREQ / SAMPLE_RATE
        self.cycle_accum = 0.0
        self.buffer = []
        self.chunk_size = AUDIO_BUFFER_SIZE
        self.channel = None

        try:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
            self.enabled = True
            self.channel = pygame.mixer.Channel(0)
        except Exception as e:
            print(f"Audio init failed: {e}")
            self.enabled = False

    def push_cycles(self, cpu_cycles):
        """Call after each CPU step with the number of CPU cycles elapsed.
        Generates audio samples at the correct rate."""
        if not self.enabled:
            return
        self.cycle_accum += cpu_cycles
        while self.cycle_accum >= self.cycles_per_sample:
            self.cycle_accum -= self.cycles_per_sample
            sample = self.apu.sample()
            # Convert float 0..1-ish to int16
            val = int(sample * 12000)
            if val > 32767:
                val = 32767
            elif val < -32768:
                val = -32768
            self.buffer.append(val)

        # When we have enough samples, queue audio
        if len(self.buffer) >= self.chunk_size:
            self._flush()

    def _flush(self):
        if not self.buffer:
            return
        arr = np.array(self.buffer[:self.chunk_size], dtype=np.int16)
        self.buffer = self.buffer[self.chunk_size:]
        
        # Get mixer config to handle mono/stereo properly
        mixer_info = pygame.mixer.get_init()
        if mixer_info and mixer_info[2] == 2:  # Stereo
            # Convert mono to stereo by duplicating the channel
            arr = np.column_stack((arr, arr))
        
        sound = pygame.sndarray.make_sound(arr)
        if self.channel and not self.channel.get_queue():
            self.channel.queue(sound)
        else:
            # If queue is full, just play (may cause slight skip)
            sound.play()

    def close(self):
        if self.enabled:
            try:
                pygame.mixer.quit()
            except Exception:
                pass


class Emulator:
    def __init__(self, rom_path, scale=3):
        self.cartridge = Cartridge(rom_path)
        self.nes = NES(self.cartridge)
        self.nes.reset()

        # Pygame display
        pygame.init()
        self.scale = scale
        self.width = 256 * scale
        self.height = 240 * scale
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(f"NES Emulator - {rom_path}")

        # NES output surface
        self.nes_surface = pygame.Surface((256, 240))

        # Audio
        self.audio = AudioStreamer(self.nes.apu)

        # Timing
        self.clock = pygame.time.Clock()
        self.target_fps = 60

        # FPS tracking
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps_time = time.time()
        self.fps = 0.0
        self.font = pygame.font.Font(None, 24)
        self.show_fps = True

        self.running = True

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_F1:
                    self.show_fps = not self.show_fps
                elif event.key in KEY_MAP:
                    button = KEY_MAP[event.key]
                    self.nes.controller1.set_button(button, True)
            elif event.type == pygame.KEYUP:
                if event.key in KEY_MAP:
                    button = KEY_MAP[event.key]
                    self.nes.controller1.set_button(button, False)

    def render(self):
        frame = self.nes.get_frame()
        # Transpose from (row, col, rgb) to pygame's (col, row, rgb)
        pygame.surfarray.blit_array(self.nes_surface, np.transpose(frame, (1, 0, 2)))
        pygame.transform.scale(self.nes_surface, (self.width, self.height), self.screen)

        if self.show_fps:
            fps_text = self.font.render(f"FPS: {self.fps:.1f}", True, (255, 255, 0))
            self.screen.blit(fps_text, (10, 10))

        pygame.display.flip()

    def update_fps(self):
        now = time.time()
        if now - self.last_fps_time >= 1.0:
            self.fps = self.frame_count / (now - self.last_fps_time)
            self.frame_count = 0
            self.last_fps_time = now

    def run(self):
        print("\n" + "=" * 50)
        print("NES Emulator Started")
        print("=" * 50)
        print("\nControls:")
        print("  Arrow Keys: D-Pad")
        print("  Z: A Button  |  X: B Button")
        print("  Enter: Start  |  Right Shift: Select")
        print("  F1: Toggle FPS  |  ESC: Quit")
        print("=" * 50 + "\n")

        # Hook audio into the NES step loop
        _orig_step = self.nes.step
        audio = self.audio

        def step_with_audio():
            cycles = _orig_step()
            audio.push_cycles(cycles)
            return cycles

        self.nes.step = step_with_audio

        while self.running:
            self.handle_input()
            self.nes.step_frame()
            self.render()
            self.clock.tick(self.target_fps)
            self.frame_count += 1
            self.update_fps()

        # Cleanup
        self.audio.close()
        pygame.quit()

        total_time = time.time() - self.start_time
        print(f"\nTotal time: {total_time:.2f}s")
        print(f"Frames: {self.nes.ppu.frame}")
        print(f"Average FPS: {self.nes.ppu.frame / max(total_time, 0.001):.2f}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <rom_file.nes> [scale]")
        sys.exit(1)

    rom_path = sys.argv[1]
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    try:
        emulator = Emulator(rom_path, scale)
        emulator.run()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
