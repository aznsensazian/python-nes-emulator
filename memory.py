"""
NES Memory Management
Handles CPU memory map with proper mirroring
"""

class Memory:
    def __init__(self, nes):
        self.nes = nes
        # 2KB internal RAM
        self.ram = bytearray(0x0800)
    
    def read(self, address):
        """Read byte from memory"""
        address &= 0xFFFF
        
        # RAM (0x0000-0x1FFF) - mirrored every 0x0800 bytes
        if address < 0x2000:
            return self.ram[address & 0x07FF]
        
        # PPU Registers (0x2000-0x3FFF) - mirrored every 8 bytes
        elif address < 0x4000:
            return self.nes.ppu.read_register(0x2000 + (address & 0x0007))
        
        # APU and I/O Registers (0x4000-0x4017)
        elif address < 0x4018:
            if address == 0x4016:
                return self.nes.controller1.read()
            elif address == 0x4017:
                return self.nes.controller2.read()
            else:
                return self.nes.apu.read_register(address)
        
        # APU and I/O functionality (0x4018-0x401F) - normally disabled
        elif address < 0x4020:
            return 0
        
        # Cartridge space (0x4020-0xFFFF)
        else:
            return self.nes.cartridge.read(address)
    
    def write(self, address, value):
        """Write byte to memory"""
        address &= 0xFFFF
        value &= 0xFF
        
        # RAM (0x0000-0x1FFF) - mirrored every 0x0800 bytes
        if address < 0x2000:
            self.ram[address & 0x07FF] = value
        
        # PPU Registers (0x2000-0x3FFF) - mirrored every 8 bytes
        elif address < 0x4000:
            self.nes.ppu.write_register(0x2000 + (address & 0x0007), value)
        
        # APU and I/O Registers (0x4000-0x4017)
        elif address < 0x4018:
            if address == 0x4014:
                # OAM DMA - copy 256 bytes from CPU page to PPU OAM
                page = value << 8
                ppu = self.nes.ppu
                oam = ppu.oam
                oa = ppu.oam_addr
                for i in range(256):
                    oam[(oa + i) & 0xFF] = self.read(page + i)
                # DMA takes 513 or 514 CPU cycles
                cpu = self.nes.cpu
                cpu.cycles += 513 + (cpu.total_cycles & 1)
            elif address == 0x4016:
                self.nes.controller1.write(value)
                self.nes.controller2.write(value)
            else:
                self.nes.apu.write_register(address, value)
        
        # APU and I/O functionality (0x4018-0x401F) - normally disabled
        elif address < 0x4020:
            pass
        
        # Cartridge space (0x4020-0xFFFF)
        else:
            self.nes.cartridge.write(address, value)
