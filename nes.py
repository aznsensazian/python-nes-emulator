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

        # APU runs at CPU speed (batched for performance)
        self.apu.clock(cycles)

        self.master_clock += cycles
        return cycles

    def step_frame(self):
        """Run until a full frame is rendered.
        Inlines the CPU step() hot loop to avoid ~9K method calls/frame."""
        cpu = self.cpu
        ppu = self.ppu
        apu = self.apu
        ppu_cycles = self._ppu_cycles
        ppu_run = ppu.run_scanline
        apu_clock = apu.clock

        # Cache CPU internals as locals
        opcodes = cpu.opcodes
        ram = cpu._ram
        cart_read = cpu._cart_read
        mem_read = cpu._mem_read
        mem_write = cpu._mem_write

        ppu.frame_ready = False
        while not ppu.frame_ready:
            # --- Inlined cpu.step() ---
            if cpu.nmi_pending:
                cpu.nmi()
                cpu.nmi_pending = False
            elif cpu.irq_pending and not (cpu.P & 0x04):
                cpu.irq()
                cpu.irq_pending = False

            # Fetch opcode
            pc = cpu.PC
            if pc >= 0x4020:
                opcode = cart_read(pc)
            elif pc < 0x2000:
                opcode = ram[pc & 0x7FF]
            else:
                opcode = mem_read(pc)
            cpu.PC = (pc + 1) & 0xFFFF

            entry = opcodes[opcode]
            if entry is None:
                cycles = 2
            else:
                instruction, addr_mode, base_cycles = entry
                addr, page_crossed = addr_mode()
                cycles = base_cycles + instruction(addr, page_crossed)

            cpu.cycles = cycles
            cpu.total_cycles += cycles
            # --- End inlined cpu.step() ---

            ppu_cycles += cycles * 3
            while ppu_cycles >= 341:
                ppu_cycles -= 341
                if ppu_run():
                    cpu.nmi_pending = True
            apu_clock(cycles)

        self._ppu_cycles = ppu_cycles

    def get_frame(self):
        return self.ppu.get_frame()
