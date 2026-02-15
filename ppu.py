"""
NES PPU (Picture Processing Unit)
Handles all graphics rendering
"""

import numpy as np

class PPU:
    def __init__(self, nes):
        self.nes = nes
        
        # PPU Memory
        self.vram = bytearray(0x0800)  # 2KB VRAM for nametables
        self.palette_ram = bytearray(0x20)  # 32 bytes for palette
        self.oam = bytearray(0x100)  # 256 bytes Object Attribute Memory
        
        # Registers
        self.ctrl = 0  # $2000
        self.mask = 0  # $2001
        self.status = 0  # $2002
        self.oam_addr = 0  # $2003
        self.scroll_x = 0
        self.scroll_y = 0
        self.addr = 0  # $2006
        self.data_buffer = 0
        
        # Internal registers
        self.v = 0  # Current VRAM address (15 bits)
        self.t = 0  # Temporary VRAM address (15 bits)
        self.x = 0  # Fine X scroll (3 bits)
        self.w = 0  # Write toggle (1 bit)
        
        # Rendering
        self.scanline = 0
        self.cycle = 0
        self.frame = 0
        self.odd_frame = False
        
        # Frame buffer (256x240 pixels)
        self.screen = np.zeros((240, 256, 3), dtype=np.uint8)
        self.frame_ready = False
        
        # NES Color Palette (NTSC)
        self.palette = np.array([
            [0x80, 0x80, 0x80], [0x00, 0x3D, 0xA6], [0x00, 0x12, 0xB0], [0x44, 0x00, 0x96],
            [0xA1, 0x00, 0x5E], [0xC7, 0x00, 0x28], [0xBA, 0x06, 0x00], [0x8C, 0x17, 0x00],
            [0x5C, 0x2F, 0x00], [0x10, 0x45, 0x00], [0x05, 0x4A, 0x00], [0x00, 0x47, 0x2E],
            [0x00, 0x41, 0x66], [0x00, 0x00, 0x00], [0x05, 0x05, 0x05], [0x05, 0x05, 0x05],
            [0xC7, 0xC7, 0xC7], [0x00, 0x77, 0xFF], [0x21, 0x55, 0xFF], [0x82, 0x37, 0xFA],
            [0xEB, 0x2F, 0xB5], [0xFF, 0x29, 0x50], [0xFF, 0x22, 0x00], [0xD6, 0x32, 0x00],
            [0xC4, 0x62, 0x00], [0x35, 0x80, 0x00], [0x05, 0x8F, 0x00], [0x00, 0x8A, 0x55],
            [0x00, 0x99, 0xCC], [0x21, 0x21, 0x21], [0x09, 0x09, 0x09], [0x09, 0x09, 0x09],
            [0xFF, 0xFF, 0xFF], [0x0F, 0xD7, 0xFF], [0x69, 0xA2, 0xFF], [0xD4, 0x80, 0xFF],
            [0xFF, 0x45, 0xF3], [0xFF, 0x61, 0x8B], [0xFF, 0x88, 0x33], [0xFF, 0x9C, 0x12],
            [0xFA, 0xBC, 0x20], [0x9F, 0xE3, 0x0E], [0x2B, 0xF0, 0x35], [0x0C, 0xF0, 0xA4],
            [0x05, 0xFB, 0xFF], [0x5E, 0x5E, 0x5E], [0x0D, 0x0D, 0x0D], [0x0D, 0x0D, 0x0D],
            [0xFF, 0xFF, 0xFF], [0xA6, 0xFC, 0xFF], [0xB3, 0xEC, 0xFF], [0xDA, 0xAB, 0xEB],
            [0xFF, 0xA8, 0xF9], [0xFF, 0xAB, 0xB3], [0xFF, 0xD2, 0xB0], [0xFF, 0xEF, 0xA6],
            [0xFF, 0xF7, 0x9C], [0xD7, 0xE8, 0x95], [0xA6, 0xED, 0xAF], [0xA2, 0xF2, 0xDA],
            [0x99, 0xFF, 0xFC], [0xDD, 0xDD, 0xDD], [0x11, 0x11, 0x11], [0x11, 0x11, 0x11]
        ], dtype=np.uint8)
    
    def reset(self):
        """Reset PPU"""
        self.ctrl = 0
        self.mask = 0
        self.status = 0x80
        self.oam_addr = 0
        self.scroll_x = 0
        self.scroll_y = 0
        self.addr = 0
        self.data_buffer = 0
        self.v = 0
        self.t = 0
        self.x = 0
        self.w = 0
        self.scanline = 0
        self.cycle = 0
        self.frame = 0
        self.odd_frame = False
    
    def read_register(self, address):
        """Read from PPU register"""
        address = 0x2000 + (address & 0x0007)
        
        if address == 0x2002:  # PPUSTATUS
            value = self.status
            self.status &= 0x7F  # Clear VBlank flag
            self.w = 0  # Reset write toggle
            return value
        
        elif address == 0x2004:  # OAMDATA
            return self.oam[self.oam_addr]
        
        elif address == 0x2007:  # PPUDATA
            value = self.data_buffer
            self.data_buffer = self.read_vram(self.v)
            
            # Palette reads are immediate
            if self.v >= 0x3F00:
                value = self.data_buffer
            
            # Increment address
            if self.ctrl & 0x04:
                self.v = (self.v + 32) & 0x7FFF
            else:
                self.v = (self.v + 1) & 0x7FFF
            
            return value
        
        return 0
    
    def write_register(self, address, value):
        """Write to PPU register"""
        address = 0x2000 + (address & 0x0007)
        value &= 0xFF
        
        if address == 0x2000:  # PPUCTRL
            self.ctrl = value
            self.t = (self.t & 0xF3FF) | ((value & 0x03) << 10)
        
        elif address == 0x2001:  # PPUMASK
            self.mask = value
        
        elif address == 0x2003:  # OAMADDR
            self.oam_addr = value
        
        elif address == 0x2004:  # OAMDATA
            self.oam[self.oam_addr] = value
            self.oam_addr = (self.oam_addr + 1) & 0xFF
        
        elif address == 0x2005:  # PPUSCROLL
            if self.w == 0:
                self.t = (self.t & 0xFFE0) | (value >> 3)
                self.x = value & 0x07
                self.w = 1
            else:
                self.t = (self.t & 0x8FFF) | ((value & 0x07) << 12)
                self.t = (self.t & 0xFC1F) | ((value & 0xF8) << 2)
                self.w = 0
        
        elif address == 0x2006:  # PPUADDR
            if self.w == 0:
                self.t = (self.t & 0x80FF) | ((value & 0x3F) << 8)
                self.w = 1
            else:
                self.t = (self.t & 0xFF00) | value
                self.v = self.t
                self.w = 0
        
        elif address == 0x2007:  # PPUDATA
            self.write_vram(self.v, value)
            # Increment address
            if self.ctrl & 0x04:
                self.v = (self.v + 32) & 0x7FFF
            else:
                self.v = (self.v + 1) & 0x7FFF
        
        elif address == 0x4014:  # OAMDMA
            # DMA transfer from CPU memory
            page = value << 8
            for i in range(256):
                self.oam[(self.oam_addr + i) & 0xFF] = self.nes.cpu.read(page + i)
            # DMA takes 513 or 514 cycles
            self.nes.cpu.cycles += 513 if (self.nes.cpu.total_cycles % 2 == 0) else 514
    
    def read_vram(self, address):
        """Read from PPU VRAM"""
        address &= 0x3FFF
        
        # Pattern tables (CHR ROM/RAM)
        if address < 0x2000:
            return self.nes.cartridge.read_chr(address)
        
        # Nametables
        elif address < 0x3F00:
            return self.vram[self.mirror_nametable(address) & 0x07FF]
        
        # Palette RAM
        else:
            addr = address & 0x1F
            if addr >= 0x10 and (addr & 0x03) == 0:
                addr -= 0x10
            return self.palette_ram[addr]
    
    def write_vram(self, address, value):
        """Write to PPU VRAM"""
        address &= 0x3FFF
        value &= 0xFF
        
        # Pattern tables (CHR ROM/RAM)
        if address < 0x2000:
            self.nes.cartridge.write_chr(address, value)
        
        # Nametables
        elif address < 0x3F00:
            self.vram[self.mirror_nametable(address) & 0x07FF] = value
        
        # Palette RAM
        else:
            addr = address & 0x1F
            if addr >= 0x10 and (addr & 0x03) == 0:
                addr -= 0x10
            self.palette_ram[addr] = value
    
    def mirror_nametable(self, address):
        """Apply nametable mirroring"""
        address = (address - 0x2000) & 0x0FFF
        table = (address // 0x0400) & 0x03
        offset = address % 0x0400
        
        mirroring = self.nes.cartridge.mirroring
        
        if mirroring == 0:  # Horizontal
            table = [0, 0, 1, 1][table]
        elif mirroring == 1:  # Vertical
            table = [0, 1, 0, 1][table]
        elif mirroring == 2:  # Single-screen A
            table = 0
        elif mirroring == 3:  # Single-screen B
            table = 1
        
        return table * 0x0400 + offset
    
    def step(self):
        """Execute one PPU cycle"""
        self.cycle += 1
        
        # Visible scanlines (0-239)
        if self.scanline < 240:
            if self.cycle <= 256 and self.cycle % 8 == 0:
                self.render_pixel()
        
        # Post-render scanline (240)
        elif self.scanline == 240:
            pass
        
        # VBlank scanlines (241-260)
        elif self.scanline == 241:
            if self.cycle == 1:
                # Set VBlank flag
                self.status |= 0x80
                if self.ctrl & 0x80:  # NMI enabled
                    self.nes.cpu.trigger_nmi()
                self.frame_ready = True
        
        # Pre-render scanline (261)
        elif self.scanline == 261:
            if self.cycle == 1:
                # Clear VBlank and sprite flags
                self.status &= 0x1F
                self.frame_ready = False
        
        # End of scanline
        if self.cycle >= 341:
            self.cycle = 0
            self.scanline += 1
            
            # End of frame
            if self.scanline >= 262:
                self.scanline = 0
                self.frame += 1
                self.odd_frame = not self.odd_frame
    
    def render_pixel(self):
        """Render current pixel"""
        if not (self.mask & 0x18):  # Rendering disabled
            return
        
        x = self.cycle - 1
        y = self.scanline
        
        if x >= 256 or y >= 240:
            return
        
        # Get background color
        bg_color = self.get_background_pixel(x, y)
        
        # Get sprite color
        sprite_color, sprite_priority = self.get_sprite_pixel(x, y)
        
        # Combine background and sprite
        if sprite_color & 0x03:
            if bg_color & 0x03 and not sprite_priority:
                color = bg_color
            else:
                color = sprite_color
        else:
            color = bg_color
        
        # Get RGB from palette
        rgb = self.palette[self.palette_ram[color] & 0x3F]
        self.screen[y, x] = rgb
    
    def get_background_pixel(self, x, y):
        """Get background pixel color"""
        if not (self.mask & 0x08):  # Background rendering disabled
            return 0
        
        # Add scroll offset
        scroll_x = self.scroll_x if x >= 8 or (self.mask & 0x02) else 0
        scroll_y = self.scroll_y
        
        px = (x + scroll_x) % 512
        py = (y + scroll_y) % 480
        
        # Get nametable
        nt_x = px // 256
        nt_y = py // 240
        nt_addr = 0x2000 + nt_y * 0x0800 + nt_x * 0x0400
        
        # Get tile position
        tile_x = (px % 256) // 8
        tile_y = (py % 240) // 8
        tile_addr = nt_addr + tile_y * 32 + tile_x
        tile_index = self.read_vram(tile_addr)
        
        # Get pattern table address
        pattern_table = 0x1000 if (self.ctrl & 0x10) else 0x0000
        pattern_addr = pattern_table + tile_index * 16
        
        # Get pixel within tile
        fine_y = (py % 240) % 8
        fine_x = (px % 256) % 8
        
        # Read pattern data
        low_byte = self.read_vram(pattern_addr + fine_y)
        high_byte = self.read_vram(pattern_addr + fine_y + 8)
        
        # Extract pixel
        bit_index = 7 - fine_x
        pixel = ((low_byte >> bit_index) & 1) | (((high_byte >> bit_index) & 1) << 1)
        
        if pixel == 0:
            return 0
        
        # Get attribute
        attr_addr = nt_addr + 0x03C0 + (tile_y // 4) * 8 + (tile_x // 4)
        attr = self.read_vram(attr_addr)
        
        # Get palette from attribute
        shift = ((tile_y & 2) << 1) | (tile_x & 2)
        palette_index = (attr >> shift) & 0x03
        
        return 0x00 + palette_index * 4 + pixel
    
    def get_sprite_pixel(self, x, y):
        """Get sprite pixel color"""
        if not (self.mask & 0x10):  # Sprite rendering disabled
            return 0, False
        
        sprite_size = 16 if (self.ctrl & 0x20) else 8
        
        for i in range(63, -1, -1):
            sprite_y = self.oam[i * 4 + 0]
            tile_index = self.oam[i * 4 + 1]
            attributes = self.oam[i * 4 + 2]
            sprite_x = self.oam[i * 4 + 3]
            
            # Check if sprite is on this scanline
            if y < sprite_y or y >= sprite_y + sprite_size:
                continue
            
            # Check if sprite is at this x position
            if x < sprite_x or x >= sprite_x + 8:
                continue
            
            # Get pixel position within sprite
            row = y - sprite_y
            col = x - sprite_x
            
            # Apply flip flags
            if attributes & 0x80:  # Flip vertically
                row = sprite_size - 1 - row
            if attributes & 0x40:  # Flip horizontally
                col = 7 - col
            
            # Get pattern table address
            if sprite_size == 8:
                pattern_table = 0x1000 if (self.ctrl & 0x08) else 0x0000
                pattern_addr = pattern_table + tile_index * 16 + row
            else:
                pattern_table = 0x1000 if (tile_index & 0x01) else 0x0000
                tile_index &= 0xFE
                if row >= 8:
                    tile_index += 1
                    row -= 8
                pattern_addr = pattern_table + tile_index * 16 + row
            
            # Read pattern data
            low_byte = self.read_vram(pattern_addr)
            high_byte = self.read_vram(pattern_addr + 8)
            
            # Extract pixel
            bit_index = 7 - col
            pixel = ((low_byte >> bit_index) & 1) | (((high_byte >> bit_index) & 1) << 1)
            
            if pixel == 0:
                continue
            
            # Get palette
            palette_index = attributes & 0x03
            priority = (attributes & 0x20) == 0
            
            return 0x10 + palette_index * 4 + pixel, priority
        
        return 0, False
    
    def get_frame(self):
        """Get current frame buffer"""
        return self.screen.copy()
