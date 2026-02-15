#!/usr/bin/env python3
"""
NES Emulator Main Entry Point
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
    pygame.K_RSHIFT: 'SELECT'
}

class Emulator:
    def __init__(self, rom_path, scale=3):
        # Load ROM
        self.cartridge = Cartridge(rom_path)
        self.nes = NES(self.cartridge)
        self.nes.reset()
        
        # Initialize pygame
        pygame.init()
        self.scale = scale
        self.width = 256 * scale
        self.height = 240 * scale
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(f"NES Emulator - {rom_path}")
        
        # Create surface for NES output
        self.nes_surface = pygame.Surface((256, 240))
        
        # Timing
        self.clock = pygame.time.Clock()
        self.target_fps = 60
        
        # Performance tracking
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps_time = time.time()
        self.fps = 0
        
        # Font for FPS display
        self.font = pygame.font.Font(None, 24)
        
        self.running = True
    
    def handle_input(self):
        """Handle keyboard input"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key in KEY_MAP:
                    button = KEY_MAP[event.key]
                    self.nes.controller1.set_button(button, True)
            
            elif event.type == pygame.KEYUP:
                if event.key in KEY_MAP:
                    button = KEY_MAP[event.key]
                    self.nes.controller1.set_button(button, False)
    
    def render(self):
        """Render frame to screen"""
        # Get frame from PPU
        frame = self.nes.get_frame()
        
        # Convert to pygame surface
        pygame.surfarray.blit_array(self.nes_surface, np.transpose(frame, (1, 0, 2)))
        
        # Scale up
        scaled = pygame.transform.scale(self.nes_surface, (self.width, self.height))
        self.screen.blit(scaled, (0, 0))
        
        # Draw FPS
        fps_text = self.font.render(f"FPS: {self.fps:.1f}", True, (255, 255, 0))
        self.screen.blit(fps_text, (10, 10))
        
        pygame.display.flip()
    
    def update_fps(self):
        """Update FPS counter"""
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            self.fps = self.frame_count / (current_time - self.last_fps_time)
            self.frame_count = 0
            self.last_fps_time = current_time
    
    def run(self):
        """Main emulation loop"""
        print("\n" + "="*50)
        print("NES Emulator Started")
        print("="*50)
        print("\nControls:")
        print("  Arrow Keys: D-Pad")
        print("  Z: A Button")
        print("  X: B Button")
        print("  Enter: Start")
        print("  Right Shift: Select")
        print("  ESC: Quit")
        print("\n" + "="*50 + "\n")
        
        while self.running:
            self.handle_input()
            
            # Run one frame
            self.nes.step_frame()
            
            # Render
            self.render()
            
            # Timing
            self.clock.tick(self.target_fps)
            self.frame_count += 1
            self.update_fps()
        
        # Cleanup
        pygame.quit()
        
        # Print statistics
        total_time = time.time() - self.start_time
        print("\n" + "="*50)
        print("Emulation Statistics")
        print("="*50)
        print(f"Total time: {total_time:.2f} seconds")
        print(f"Frames: {self.nes.ppu.frame}")
        print(f"Average FPS: {self.nes.ppu.frame / total_time:.2f}")
        print(f"CPU cycles: {self.nes.cpu.total_cycles:,}")
        print("="*50 + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <rom_file.nes> [scale]")
        print("  scale: Window scale factor (default: 3)")
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
