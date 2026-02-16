"""
Main NES Emulator
Coordinates all components - optimized with scanline-based PPU stepping
"""

from cpu import CPU
from ppu import PPU
from apu import APU
from memory import Memory
from controller import Controller


class NES:
    def __init__(self, cartridge):
        self.cartridge = cartridge
        self.memory = Memory(self)
        self.cpu = CPU(self.memory)
        self.ppu = PPU(self)
        self.apu = APU(self)
        self.controller1 = Controller()
        self.controller2 = Controller()
        self.master_clock = 0

        # PPU cycle debt tracker for scanline batching
        self._ppu_cycles = 0

    def reset(self):
        self.cpu.reset()
        self.ppu.reset()
        self.apu.reset()
        self.master_clock = 0
        self._ppu_cycles = 0

    def step(self):
        """Step one CPU instruction, batch PPU scanlines."""
        cycles = self.cpu.step()

        # Accumulate PPU cycles (3 per CPU cycle)
        self._ppu_cycles += cycles * 3

        # Drain full scanlines (341 PPU cycles each)
        while self._ppu_cycles >= 341:
            self._ppu_cycles -= 341
            nmi = self.ppu.run_scanline()
            if nmi:
                self.cpu.trigger_nmi()

        # APU runs at CPU speed
        for _ in range(cycles):
            self.apu.step()

        self.master_clock += cycles
        return cycles

    def step_frame(self):
        """Run until a full frame is rendered."""
        self.ppu.frame_ready = False
        while not self.ppu.frame_ready:
            self.step()

    def get_frame(self):
        return self.ppu.get_frame()
