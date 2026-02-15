"""
Main NES Emulator
Coordinates all components
"""

from cpu import CPU
from ppu import PPU
from apu import APU
from memory import Memory
from controller import Controller

class NES:
    def __init__(self, cartridge):
        self.cartridge = cartridge
        
        # Initialize components
        self.memory = Memory(self)
        self.cpu = CPU(self.memory)
        self.ppu = PPU(self)
        self.apu = APU(self)
        self.controller1 = Controller()
        self.controller2 = Controller()
        
        # Timing
        self.master_clock = 0
        
    def reset(self):
        """Reset the console"""
        self.cpu.reset()
        self.ppu.reset()
        self.apu.reset()
        self.master_clock = 0
    
    def step(self):
        """Step one CPU instruction"""
        cycles = self.cpu.step()
        
        # PPU runs 3x faster than CPU
        for _ in range(cycles * 3):
            self.ppu.step()
        
        # APU runs at CPU speed
        for _ in range(cycles):
            self.apu.step()
        
        self.master_clock += cycles
        
        return cycles
    
    def step_frame(self):
        """Run until a full frame is rendered"""
        self.ppu.frame_ready = False
        while not self.ppu.frame_ready:
            self.step()
    
    def get_frame(self):
        """Get current frame buffer"""
        return self.ppu.get_frame()
