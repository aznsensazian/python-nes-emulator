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

        # Tile-row cache: invalidated each scanline (cheap dict)
        self._tile_cache = {}

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
            # pre-render
            self.status &= 0x1F
            self.frame_ready = False

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
        elif address == 0x4014:  # OAM DMA
            page = value << 8
            cpu = self.nes.cpu
            oam = self.oam
            oa = self.oam_addr
            for i in range(256):
                oam[(oa + i) & 0xFF] = cpu.read(page + i)
            cpu.cycles += 513 if (cpu.total_cycles & 1 == 0) else 514

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

        # -- Background --
        bg_pixels = self._render_bg_scanline(y, read_chr)

        # -- Sprites --
        sprite_pixels, sprite_prio, sprite_opaque = self._render_sprite_scanline(y, read_chr)

        # -- Compose --
        for px in range(256):
            bg_val = bg_pixels[px]
            sp_val = sprite_pixels[px]
            sp_opq = sprite_opaque[px]

            if sp_opq:
                if (bg_val & 3) and sprite_prio[px]:
                    # bg priority
                    color = bg_val
                else:
                    color = sp_val
            else:
                color = bg_val

            screen_row[px] = palette_rgb[palette_ram[color] & 0x3F]

    def _render_bg_scanline(self, y, read_chr):
        """Return 256-element list of palette indices for background.
        Processes tile-by-tile to minimise VRAM reads."""
        bg = [0] * 256
        if not (self.mask & 0x08):
            return bg

        sx = self.scroll_x
        sy = self.scroll_y
        base_nt = (self.ctrl & 3)
        pattern_table = 0x1000 if (self.ctrl & 0x10) else 0
        clip_left = not (self.mask & 0x02)

        eff_y = (y + sy) % 480
        nt_row = 0 if eff_y < 240 else 1
        local_y = eff_y if eff_y < 240 else eff_y - 240
        tile_row = local_y >> 3
        fine_y = local_y & 7

        vram = self.vram
        mirror_nt = self.mirror_nametable
        base_nt_h = base_nt & 1
        base_nt_v = (base_nt >> 1) & 1

        # Cache: key = (nt_index, tile_col) -> (lo, hi, pal_base)
        # Avoid re-reading same tile data when fine_x != 0
        _cache = {}

        px = 0
        while px < 256:
            eff_x = (px + sx) & 511  # mod 512
            nt_col = 1 if eff_x >= 256 else 0
            local_x = eff_x & 255

            nt_index = (base_nt_h ^ nt_col) | ((base_nt_v ^ nt_row) << 1)
            tile_col = local_x >> 3
            fine_x = local_x & 7

            # How many pixels left in this tile from fine_x?
            run = 8 - fine_x
            if px + run > 256:
                run = 256 - px

            cache_key = (nt_index, tile_col)
            cached = _cache.get(cache_key)
            if cached is None:
                nt_base = 0x2000 + nt_index * 0x400
                tile_idx = vram[mirror_nt(nt_base + tile_row * 32 + tile_col)]
                pat_addr = pattern_table + tile_idx * 16 + fine_y
                lo = read_chr(pat_addr)
                hi = read_chr(pat_addr + 8)

                attr_addr = nt_base + 0x3C0 + (tile_row >> 2) * 8 + (tile_col >> 2)
                attr = vram[mirror_nt(attr_addr)]
                shift = ((tile_row & 2) << 1) | (tile_col & 2)
                pal_base = ((attr >> shift) & 3) << 2  # * 4
                cached = (lo, hi, pal_base)
                _cache[cache_key] = cached
            else:
                lo, hi, pal_base = cached

            for i in range(run):
                cpx = px + i
                if cpx < 8 and clip_left:
                    continue
                bit = 7 - (fine_x + i)
                pixel = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)
                if pixel:
                    bg[cpx] = pal_base + pixel

            px += run

        return bg

    def _render_sprite_scanline(self, y, read_chr):
        """Return (pixels[256], priority[256], opaque[256]) for sprites."""
        pixels = [0] * 256
        prio = [False] * 256
        opaque = [False] * 256

        if not (self.mask & 0x10):
            return pixels, prio, opaque

        sprite_size = 16 if (self.ctrl & 0x20) else 8
        oam = self.oam
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

            for bit in range(8):
                px_x = sprite_x + bit
                if px_x >= 256:
                    break
                if opaque[px_x]:
                    continue  # higher priority sprite already here

                col = (7 - bit) if not flip_h else bit
                pixel = ((lo >> col) & 1) | (((hi >> col) & 1) << 1)
                if pixel == 0:
                    continue

                pixels[px_x] = 0x10 + pal_idx * 4 + pixel
                prio[px_x] = bool(behind_bg)
                opaque[px_x] = True

        return pixels, prio, opaque

    def get_frame(self):
        return self.screen
