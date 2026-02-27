"""
NES Cartridge and ROM loader
Supports iNES format and multiple mappers
"""

class Cartridge:
    def __init__(self, filename):
        self.filename = filename
        self.prg_rom = bytearray()
        self.chr_rom = bytearray()
        self.chr_ram = bytearray()
        self.prg_ram = bytearray(0x2000)  # 8KB PRG RAM
        self.mapper_number = 0
        self.mirroring = 0  # 0=horizontal, 1=vertical
        self.battery_backed = False
        self.has_trainer = False
        self.mapper = None
        
        self.load_rom(filename)
    
    def load_rom(self, filename):
        """Load iNES format ROM"""
        with open(filename, 'rb') as f:
            # Read header (16 bytes)
            header = f.read(16)
            
            # Check magic number "NES\x1A"
            if header[0:4] != b'NES\x1A':
                raise ValueError("Not a valid iNES ROM file")
            
            # Parse header
            prg_rom_size = header[4] * 16384  # 16KB units
            chr_rom_size = header[5] * 8192   # 8KB units
            
            flags6 = header[6]
            flags7 = header[7]
            
            self.mirroring = flags6 & 1
            self.battery_backed = (flags6 & 2) != 0
            self.has_trainer = (flags6 & 4) != 0
            
            # Mapper number is in upper nibble of flags6 and flags7
            self.mapper_number = ((flags7 & 0xF0) | (flags6 >> 4))
            
            # Skip trainer if present
            if self.has_trainer:
                f.read(512)
            
            # Read PRG ROM
            self.prg_rom = bytearray(f.read(prg_rom_size))
            
            # Read CHR ROM (or create CHR RAM if size is 0)
            if chr_rom_size > 0:
                self.chr_rom = bytearray(f.read(chr_rom_size))
            else:
                self.chr_ram = bytearray(8192)  # 8KB CHR RAM
            
            print(f"Loaded ROM: {filename}")
            print(f"  PRG ROM: {len(self.prg_rom)} bytes")
            print(f"  CHR ROM: {len(self.chr_rom)} bytes")
            print(f"  Mapper: {self.mapper_number}")
            print(f"  Mirroring: {'Vertical' if self.mirroring else 'Horizontal'}")
            
            # Create mapper
            self.create_mapper()
    
    def create_mapper(self):
        """Create appropriate mapper"""
        if self.mapper_number == 0:
            self.mapper = Mapper0(self)
        elif self.mapper_number == 1:
            self.mapper = Mapper1(self)
        elif self.mapper_number == 2:
            self.mapper = Mapper2(self)
        elif self.mapper_number == 3:
            self.mapper = Mapper3(self)
        else:
            raise ValueError(f"Unsupported mapper: {self.mapper_number}")
    
    def read(self, address):
        """Read from cartridge (CPU address space)"""
        return self.mapper.read(address)
    
    def write(self, address, value):
        """Write to cartridge (CPU address space)"""
        self.mapper.write(address, value)
    
    def read_chr(self, address):
        """Read from CHR ROM/RAM"""
        return self.mapper.read_chr(address)
    
    def write_chr(self, address, value):
        """Write to CHR ROM/RAM"""
        self.mapper.write_chr(address, value)


class Mapper0:
    """Mapper 0 (NROM) - No mapper chip"""
    def __init__(self, cartridge):
        self.cartridge = cartridge
        self.prg_banks = len(cartridge.prg_rom) // 16384
        # Pre-compute for fast read (avoids per-read branch + attribute chain)
        self._prg_rom = cartridge.prg_rom
        self._prg_mask = 0x3FFF if self.prg_banks == 1 else 0x7FFF
        # Cache CHR source (avoids len() check per read)
        self._chr = cartridge.chr_rom if len(cartridge.chr_rom) > 0 else cartridge.chr_ram
        self._has_chr_ram = len(cartridge.chr_ram) > 0

    def read(self, address):
        if address >= 0x8000:
            return self._prg_rom[(address - 0x8000) & self._prg_mask]
        elif address >= 0x6000:
            return self.cartridge.prg_ram[address - 0x6000]
        return 0

    def write(self, address, value):
        if address >= 0x6000 and address < 0x8000:
            # PRG RAM
            self.cartridge.prg_ram[address - 0x6000] = value

    def read_chr(self, address):
        return self._chr[address & 0x1FFF]

    def write_chr(self, address, value):
        if self._has_chr_ram:
            self.cartridge.chr_ram[address & 0x1FFF] = value


class Mapper1:
    """Mapper 1 (MMC1) - Most common mapper"""
    def __init__(self, cartridge):
        self.cartridge = cartridge
        self.shift_register = 0x10
        self.control = 0x0C
        self.chr_bank_0 = 0
        self.chr_bank_1 = 0
        self.prg_bank = 0
        
        self.prg_banks = len(cartridge.prg_rom) // 16384
        self.chr_banks = len(cartridge.chr_rom) // 4096 if len(cartridge.chr_rom) > 0 else 2
    
    def write(self, address, value):
        if address < 0x8000:
            if address >= 0x6000:
                # PRG RAM
                self.cartridge.prg_ram[address - 0x6000] = value
            return
        
        # Reset shift register on bit 7
        if value & 0x80:
            self.shift_register = 0x10
            self.control |= 0x0C
            return
        
        # Write to shift register
        complete = (self.shift_register & 1) != 0
        self.shift_register >>= 1
        self.shift_register |= (value & 1) << 4
        
        if complete:
            self.write_register(address, self.shift_register)
            self.shift_register = 0x10
    
    def write_register(self, address, value):
        """Write to internal register"""
        if address < 0xA000:
            # Control
            self.control = value & 0x1F
            mirroring = value & 3
            if mirroring == 0:
                self.cartridge.mirroring = 2  # Single-screen A
            elif mirroring == 1:
                self.cartridge.mirroring = 3  # Single-screen B
            elif mirroring == 2:
                self.cartridge.mirroring = 1  # Vertical
            else:
                self.cartridge.mirroring = 0  # Horizontal
        
        elif address < 0xC000:
            # CHR bank 0
            self.chr_bank_0 = value & 0x1F
        
        elif address < 0xE000:
            # CHR bank 1
            self.chr_bank_1 = value & 0x1F
        
        else:
            # PRG bank
            self.prg_bank = value & 0x0F
    
    def read(self, address):
        if address >= 0x8000:
            # PRG ROM
            prg_mode = (self.control >> 2) & 3
            prg_len = len(self.cartridge.prg_rom)

            if prg_mode == 0 or prg_mode == 1:
                # 32KB mode
                bank32 = max(1, self.prg_banks // 2)
                bank = (self.prg_bank >> 1) % bank32
                offset = bank * 32768 + (address - 0x8000)
                return self.cartridge.prg_rom[offset % prg_len]

            elif prg_mode == 2:
                # Fix first bank
                if address < 0xC000:
                    return self.cartridge.prg_rom[(address - 0x8000) % prg_len]
                else:
                    bank = self.prg_bank % self.prg_banks
                    offset = bank * 16384 + (address - 0xC000)
                    return self.cartridge.prg_rom[offset % prg_len]

            else:  # prg_mode == 3
                # Fix last bank
                if address < 0xC000:
                    bank = self.prg_bank % self.prg_banks
                    offset = bank * 16384 + (address - 0x8000)
                    return self.cartridge.prg_rom[offset % prg_len]
                else:
                    last_bank = self.prg_banks - 1
                    offset = last_bank * 16384 + (address - 0xC000)
                    return self.cartridge.prg_rom[offset % prg_len]

        elif address >= 0x6000:
            # PRG RAM
            return self.cartridge.prg_ram[address - 0x6000]

        return 0
    
    def read_chr(self, address):
        if len(self.cartridge.chr_rom) > 0:
            chr_mode = (self.control >> 4) & 1
            chr_len = len(self.cartridge.chr_rom)

            if chr_mode == 0:
                # 8KB mode
                bank8 = max(1, self.chr_banks // 2)
                bank = (self.chr_bank_0 >> 1) % bank8
                offset = bank * 8192 + address
                return self.cartridge.chr_rom[offset % chr_len]
            else:
                # 4KB mode
                if address < 0x1000:
                    bank = self.chr_bank_0 % max(1, self.chr_banks)
                    offset = bank * 4096 + address
                    return self.cartridge.chr_rom[offset % chr_len]
                else:
                    bank = self.chr_bank_1 % max(1, self.chr_banks)
                    offset = bank * 4096 + (address - 0x1000)
                    return self.cartridge.chr_rom[offset % chr_len]
        else:
            return self.cartridge.chr_ram[address & 0x1FFF]
    
    def write_chr(self, address, value):
        if len(self.cartridge.chr_ram) > 0:
            self.cartridge.chr_ram[address & 0x1FFF] = value


class Mapper2:
    """Mapper 2 (UxROM) - Switchable PRG ROM"""
    def __init__(self, cartridge):
        self.cartridge = cartridge
        self.prg_bank = 0
        self.prg_banks = len(cartridge.prg_rom) // 16384
    
    def read(self, address):
        if address >= 0xC000:
            # Last bank fixed
            last_bank = self.prg_banks - 1
            return self.cartridge.prg_rom[last_bank * 16384 + (address - 0xC000)]
        elif address >= 0x8000:
            # Switchable bank
            bank = self.prg_bank % self.prg_banks
            return self.cartridge.prg_rom[bank * 16384 + (address - 0x8000)]
        elif address >= 0x6000:
            # PRG RAM
            return self.cartridge.prg_ram[address - 0x6000]
        return 0
    
    def write(self, address, value):
        if address >= 0x8000:
            # Bank select
            self.prg_bank = value & 0x0F
        elif address >= 0x6000:
            # PRG RAM
            self.cartridge.prg_ram[address - 0x6000] = value
    
    def read_chr(self, address):
        if len(self.cartridge.chr_rom) > 0:
            return self.cartridge.chr_rom[address & 0x1FFF]
        else:
            return self.cartridge.chr_ram[address & 0x1FFF]
    
    def write_chr(self, address, value):
        if len(self.cartridge.chr_ram) > 0:
            self.cartridge.chr_ram[address & 0x1FFF] = value


class Mapper3:
    """Mapper 3 (CNROM) - Switchable CHR ROM"""
    def __init__(self, cartridge):
        self.cartridge = cartridge
        self.chr_bank = 0
        self.prg_banks = len(cartridge.prg_rom) // 16384
        self.chr_banks = len(cartridge.chr_rom) // 8192
    
    def read(self, address):
        if address >= 0x8000:
            # PRG ROM
            if self.prg_banks == 1:
                # Mirror for 16KB ROM
                return self.cartridge.prg_rom[(address - 0x8000) & 0x3FFF]
            else:
                # 32KB ROM
                return self.cartridge.prg_rom[address - 0x8000]
        elif address >= 0x6000:
            # PRG RAM
            return self.cartridge.prg_ram[address - 0x6000]
        return 0
    
    def write(self, address, value):
        if address >= 0x8000:
            # CHR bank select
            self.chr_bank = value & 0x03
        elif address >= 0x6000:
            # PRG RAM
            self.cartridge.prg_ram[address - 0x6000] = value
    
    def read_chr(self, address):
        bank = self.chr_bank % self.chr_banks
        return self.cartridge.chr_rom[bank * 8192 + address]
    
    def write_chr(self, address, value):
        # CHR ROM is read-only
        pass
