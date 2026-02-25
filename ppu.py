"""
NES PPU (Picture Processing Unit)
Optimized scanline-based rendering with tile caching
"""

import numpy as np

# NES system palette - pre-computed as flat lookup (64 entries x 3 RGB)
_NES_PALETTE = np.array([
    0x80,0x80,0x80, 0x00,0x3D,0xA6, 0x00,0x12,0xB0, 0x44,0x00,0x96,
    0xA1,0x00,0x5E, 0xC7,0x00,0x28, 0xBA,0x06,0x00, 0x8C,0x17,0x00,
    0x5C,0x2F,0x00, 0x10,0x45,0x00, 0x05,0x4A,0x00, 0x00,0x47,0x2E,
    0x00,0x41,0x66, 0x00,0x00,0x00, 0x05,0x05,0x05, 0x05,0x05,0x05,
    0xC7,0xC7,0xC7, 0x00,0x77,0xFF, 0x21,0x55,0xFF, 0x82,0x37,0xFA,
    0xEB,0x2F,0xB5, 0xFF,0x29,0x50, 0xFF,0x22,0x00, 0xD6,0x32,0x00,
    0xC4,0x62,0x00, 0x35,0x80,0x00, 0x05,0x8F,0x00, 0x00,0x8A,0x55,
    0x00,0x99,0xCC, 0x21,0x21,0x21, 0x09,0x09,0x09, 0x09,0x09,0x09,
    0xFF,0xFF,0xFF, 0x0F,0xD7,0xFF, 0x69,0xA2,0xFF, 0xD4,0x80,0xFF,
    0xFF,0x45,0xF3, 0xFF,0x61,0x8B, 0xFF,0x88,0x33, 0xFF,0x9C,0x12,
    0xFA,0xBC,0x20, 0x9F,0xE3,0x0E, 0x2B,0xF0,0x35, 0x0C,0xF0,0xA4,
    0x05,0xFB,0xFF, 0x5E,0x5E,0x5E, 0x0D,0x0D,0x0D, 0x0D,0x0D,0x0D,
    0xFF,0xFF,0xFF, 0xA6,0xFC,0xFF, 0xB3,0xEC,0xFF, 0xDA,0xAB,0xEB,
    0xFF,0xA8,0xF9, 0xFF,0xAB,0xB3, 0xFF,0xD2,0xB0, 0xFF,0xEF,0xA6,
    0xFF,0xF7,0x9C, 0xD7,0xE8,0x95, 0xA6,0xED,0xAF, 0xA2,0xF2,0xDA,
    0x99,0xFF,0xFC, 0xDD,0xDD,0xDD, 0x11,0x11,0x11, 0x11,0x11,0x11,
], dtype=np.uint8).reshape(64, 3)

# Pre-computed bitplane decode: for each byte, the 8 pixel bit values (MSB first)
_BIT_DECODE = [None] * 256
for _b in range(256):
    _BIT_DECODE[_b] = ((_b >> 7) & 1, (_b >> 6) & 1, (_b >> 5) & 1, (_b >> 4) & 1,
                        (_b >> 3) & 1, (_b >> 2) & 1, (_b >> 1) & 1, _b & 1)


class PPU:
    def __init__(self, nes):
        self.nes = nes

        # PPU Memory
        self.vram = bytearray(0x0800)
        self.palette_ram = bytearray(0x20)
        self.oam = bytearray(0x100)

        # Registers
        self.ctrl = 0
        self.mask = 0
        self.status = 0
        self.oam_addr = 0
        self.scroll_x = 0
        self.scroll_y = 0
        self.addr = 0
        self.data_buffer = 0

        # Internal scroll/address registers
        self.v = 0
        self.t = 0
        self.x = 0
        self.w = 0

        # Scanline / frame tracking
        self.scanline = -1  # start at pre-render
        self.cycle = 0
        self.frame = 0
        self.odd_frame = False
        self.frame_ready = False

        # Frame buffer
        self.screen = np.zeros((240, 256, 3), dtype=np.uint8)

        # Pre-computed palette reference
        self.palette = _NES_PALETTE

        # Nametable mirror LUT (built on first use / when mirroring changes)
        self._mirror_mode = -1
        self._nt_map = [0, 0, 0, 0]  # base offsets into self.vram for each NT

        # Pre-allocated scanline buffers (reused every scanline to avoid allocations)
        self._bg_pixels = [0] * 256
        self._sp_pixels = [0] * 256
        self._sp_prio = [0] * 256
        self._sp_opaque = [0] * 256
        self._sp0_opaque = [0] * 256

        # Pre-computed bit decode table: byte -> tuple of 8 bit values (bit7..bit0)
        self._bit_decode = _BIT_DECODE

    # ----------------------------------------------------------------
    # Public API used by NES to advance the PPU
    # ----------------------------------------------------------------

    def reset(self):
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
        self.scanline = -1
        self.cycle = 0
        self.frame = 0
        self.odd_frame = False
        self.frame_ready = False
        self._mirror_mode = -1

    def run_scanline(self):
        """Advance the PPU by one full scanline (341 cycles).
        Returns True when VBlank NMI should fire."""
        sl = self.scanline
        nmi = False

        if 0 <= sl < 240:
            # visible scanline – render it
            if self.mask & 0x18:
                self._render_scanline(sl)
        elif sl == 241:
            self.status |= 0x80
            self.frame_ready = True
            if self.ctrl & 0x80:
                nmi = True
        elif sl == 261:
            # pre-render: clear VBlank, sprite 0 hit, sprite overflow
            self.status &= 0x1F
            self.frame_ready = False
            # Copy all of t to v at pre-render scanline (when rendering enabled)
            if self.mask & 0x18:
                self.v = self.t

        # advance scanline
        self.scanline += 1
        if self.scanline > 261:
            self.scanline = 0
            self.frame += 1
            self.odd_frame = not self.odd_frame

        return nmi

    # keep step() for compatibility but it just counts cycles
    def step(self):
        self.cycle += 1
        if self.cycle >= 341:
            self.cycle = 0
            nmi = self.run_scanline()
            if nmi:
                self.nes.cpu.trigger_nmi()

    # ----------------------------------------------------------------
    # Register read/write  (unchanged logic, minor speed tweaks)
    # ----------------------------------------------------------------

    def read_register(self, address):
        reg = address & 7
        if reg == 2:  # PPUSTATUS
            v = self.status
            self.status &= 0x7F
            self.w = 0
            return v
        if reg == 4:  # OAMDATA
            return self.oam[self.oam_addr]
        if reg == 7:  # PPUDATA
            v = self.data_buffer
            self.data_buffer = self.read_vram(self.v)
            if self.v >= 0x3F00:
                v = self.data_buffer
            self.v = (self.v + (32 if self.ctrl & 4 else 1)) & 0x7FFF
            return v
        return 0

    def write_register(self, address, value):
        reg = address & 7
        value &= 0xFF

        if reg == 0:  # PPUCTRL
            self.ctrl = value
            self.t = (self.t & 0xF3FF) | ((value & 3) << 10)
        elif reg == 1:  # PPUMASK
            self.mask = value
        elif reg == 3:  # OAMADDR
            self.oam_addr = value
        elif reg == 4:  # OAMDATA
            self.oam[self.oam_addr] = value
            self.oam_addr = (self.oam_addr + 1) & 0xFF
        elif reg == 5:  # PPUSCROLL
            if self.w == 0:
                self.t = (self.t & 0xFFE0) | (value >> 3)
                self.x = value & 7
                self.scroll_x = value
                self.w = 1
            else:
                self.t = (self.t & 0x8FFF) | ((value & 7) << 12)
                self.t = (self.t & 0xFC1F) | ((value & 0xF8) << 2)
                self.scroll_y = value
                self.w = 0
        elif reg == 6:  # PPUADDR
            if self.w == 0:
                self.t = (self.t & 0x80FF) | ((value & 0x3F) << 8)
                self.w = 1
            else:
                self.t = (self.t & 0xFF00) | value
                self.v = self.t
                self.w = 0
        elif reg == 7:  # PPUDATA
            self.write_vram(self.v, value)
            self.v = (self.v + (32 if self.ctrl & 4 else 1)) & 0x7FFF

    # ----------------------------------------------------------------
    # VRAM access helpers
    # ----------------------------------------------------------------

    def _update_nt_map(self):
        m = self.nes.cartridge.mirroring
        if m == self._mirror_mode:
            return
        self._mirror_mode = m
        if m == 0:    # horizontal
            self._nt_map = [0, 0, 0x400, 0x400]
        elif m == 1:  # vertical
            self._nt_map = [0, 0x400, 0, 0x400]
        elif m == 2:  # single A
            self._nt_map = [0, 0, 0, 0]
        else:         # single B
            self._nt_map = [0x400, 0x400, 0x400, 0x400]

    def mirror_nametable(self, address):
        address = (address - 0x2000) & 0x0FFF
        table = address >> 10
        offset = address & 0x3FF
        m = self.nes.cartridge.mirroring
        if m == 0:
            table = [0, 0, 1, 1][table]
        elif m == 1:
            table = [0, 1, 0, 1][table]
        elif m == 2:
            table = 0
        elif m == 3:
            table = 1
        return table * 0x400 + offset

    def read_vram(self, address):
        address &= 0x3FFF
        if address < 0x2000:
            return self.nes.cartridge.read_chr(address)
        if address < 0x3F00:
            return self.vram[self.mirror_nametable(address)]
        addr = address & 0x1F
        if addr >= 0x10 and (addr & 3) == 0:
            addr -= 0x10
        return self.palette_ram[addr]

    def write_vram(self, address, value):
        address &= 0x3FFF
        value &= 0xFF
        if address < 0x2000:
            self.nes.cartridge.write_chr(address, value)
        elif address < 0x3F00:
            self.vram[self.mirror_nametable(address)] = value
        else:
            addr = address & 0x1F
            if addr >= 0x10 and (addr & 3) == 0:
                addr -= 0x10
            self.palette_ram[addr] = value

    # ----------------------------------------------------------------
    # Scanline renderer (the hot path)
    # ----------------------------------------------------------------

    def _render_scanline(self, y):
        """Render one scanline into self.screen[y]."""
        screen_row = self.screen[y]
        palette_ram = self.palette_ram
        palette_rgb = self.palette
        read_chr = self.nes.cartridge.read_chr

        # Copy horizontal scroll bits from t to v at start of each visible scanline
        self.v = (self.v & ~0x041F) | (self.t & 0x041F)

        # -- Background (writes into self._bg_pixels) --
        bg = self._bg_pixels
        self._render_bg_scanline(y, read_chr)

        # -- Sprites (writes into self._sp_* buffers) --
        sp_pixels = self._sp_pixels
        sp_prio = self._sp_prio
        sp_opaque = self._sp_opaque
        sp0 = self._sp0_opaque
        self._render_sprite_scanline(y, read_chr)

        # -- Sprite 0 hit detection --
        if not (self.status & 0x40):  # Not already set this frame
            if (self.mask & 0x18) == 0x18:  # Both bg and sprites enabled
                both_left = (self.mask & 0x06) == 0x06
                start = 0 if both_left else 8
                for px in range(start, 255):  # x=255 doesn't trigger
                    if sp0[px] and (bg[px] & 3):
                        self.status |= 0x40
                        break

        # -- Compose (hot loop - all locals for speed) --
        for px in range(256):
            bg_val = bg[px]
            if sp_opaque[px]:
                if (bg_val & 3) and sp_prio[px]:
                    color = bg_val
                else:
                    color = sp_pixels[px]
            else:
                color = bg_val
            screen_row[px] = palette_rgb[palette_ram[color] & 0x3F]

        # Y increment at end of visible scanline
        self._y_increment()

    def _render_bg_scanline(self, y, read_chr):
        """Render background into self._bg_pixels using v register for scroll."""
        bg = self._bg_pixels
        # Clear buffer
        for i in range(256):
            bg[i] = 0

        if not (self.mask & 0x08):
            return

        # Extract scroll position from v register
        v = self.v
        coarse_x = v & 0x1F
        coarse_y = (v >> 5) & 0x1F
        fine_y = (v >> 12) & 0x7
        nt_h = (v >> 10) & 1
        nt_v = (v >> 11) & 1
        fine_x = self.x

        pattern_table = 0x1000 if (self.ctrl & 0x10) else 0
        clip_left = not (self.mask & 0x02)

        vram = self.vram
        mirror_nt = self.mirror_nametable
        bit_decode = self._bit_decode

        px = 0
        tile_col = coarse_x
        cur_nt_h = nt_h
        first_tile = True

        while px < 256:
            nt_index = cur_nt_h | (nt_v << 1)
            nt_base = 0x2000 + nt_index * 0x400

            tile_idx = vram[mirror_nt(nt_base + coarse_y * 32 + tile_col)]
            pat_addr = pattern_table + tile_idx * 16 + fine_y
            lo = read_chr(pat_addr)
            hi = read_chr(pat_addr + 8)

            attr_addr = nt_base + 0x3C0 + (coarse_y >> 2) * 8 + (tile_col >> 2)
            attr = vram[mirror_nt(attr_addr)]
            shift = ((coarse_y & 2) << 1) | (tile_col & 2)
            pal_base = ((attr >> shift) & 3) << 2

            lo_bits = bit_decode[lo]
            hi_bits = bit_decode[hi]

            start = fine_x if first_tile else 0
            first_tile = False

            for i in range(start, 8):
                if px >= 256:
                    break
                if not (px < 8 and clip_left):
                    pixel = lo_bits[i] | (hi_bits[i] << 1)
                    if pixel:
                        bg[px] = pal_base + pixel
                px += 1

            tile_col += 1
            if tile_col >= 32:
                tile_col = 0
                cur_nt_h ^= 1

    def _y_increment(self):
        """Increment fine Y in v register, wrapping to coarse Y as needed."""
        if (self.v & 0x7000) != 0x7000:
            self.v += 0x1000  # increment fine Y
        else:
            self.v &= ~0x7000  # fine Y = 0
            y = (self.v & 0x03E0) >> 5  # coarse Y
            if y == 29:
                y = 0
                self.v ^= 0x0800  # switch vertical nametable
            elif y == 31:
                y = 0  # don't toggle nametable at 31
            else:
                y += 1
            self.v = (self.v & ~0x03E0) | (y << 5)

    def _render_sprite_scanline(self, y, read_chr):
        """Render sprites into pre-allocated self._sp_* buffers."""
        pixels = self._sp_pixels
        prio = self._sp_prio
        opaque = self._sp_opaque
        sprite0 = self._sp0_opaque

        # Clear buffers
        for i in range(256):
            pixels[i] = 0
            prio[i] = 0
            opaque[i] = 0
            sprite0[i] = 0

        if not (self.mask & 0x10):
            return

        sprite_size = 16 if (self.ctrl & 0x20) else 8
        oam = self.oam
        bit_decode = self._bit_decode
        count = 0

        for i in range(64):
            base = i << 2
            sy = oam[base]
            if sy >= 0xEF:
                continue
            sprite_y = sy + 1
            if y < sprite_y or y >= sprite_y + sprite_size:
                continue
            count += 1
            if count > 8:
                break

            tile_idx = oam[base + 1]
            attr = oam[base + 2]
            sprite_x = oam[base + 3]
            flip_h = attr & 0x40
            flip_v = attr & 0x80
            behind_bg = attr & 0x20
            pal_idx = attr & 3

            row = y - sprite_y
            if flip_v:
                row = sprite_size - 1 - row

            if sprite_size == 8:
                pt = 0x1000 if (self.ctrl & 0x08) else 0
                pat_addr = pt + tile_idx * 16 + row
            else:
                pt = 0x1000 if (tile_idx & 1) else 0
                ti = tile_idx & 0xFE
                if row >= 8:
                    ti += 1
                    row -= 8
                pat_addr = pt + ti * 16 + row

            lo = read_chr(pat_addr)
            hi = read_chr(pat_addr + 8)
            lo_bits = bit_decode[lo]
            hi_bits = bit_decode[hi]
            is_sprite0 = (i == 0)

            for bit in range(8):
                px_x = sprite_x + bit
                if px_x >= 256:
                    break
                if opaque[px_x]:
                    continue

                col = (7 - bit) if not flip_h else bit
                pixel = lo_bits[col] | (hi_bits[col] << 1)
                if pixel == 0:
                    continue

                pixels[px_x] = 0x10 + pal_idx * 4 + pixel
                prio[px_x] = behind_bg
                opaque[px_x] = 1
                if is_sprite0:
                    sprite0[px_x] = 1

    def get_frame(self):
        return self.screen
