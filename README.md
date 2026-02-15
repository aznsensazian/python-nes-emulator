# Python NES Emulator

A complete Nintendo Entertainment System (NES) emulator written in Python.

## Features

- **Full 6502 CPU Emulation**: All official opcodes plus common unofficial opcodes
- **PPU (Picture Processing Unit)**: Complete graphics rendering with sprite support
- **APU (Audio Processing Unit)**: Basic audio channel support
- **Multiple Mappers**: Support for Mapper 0 (NROM), 1 (MMC1), 2 (UxROM), and 3 (CNROM)
- **Controller Input**: Keyboard mapping for NES controller
- **High Compatibility**: Tested with popular NES ROMs

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/python-nes-emulator.git
cd python-nes-emulator

# Install dependencies
pip install -r requirements.txt
```

## Requirements

- Python 3.8+
- pygame
- numpy

## Usage

```bash
python main.py path/to/rom.nes
```

### Controls

- **Arrow Keys**: D-Pad
- **Z**: A Button
- **X**: B Button
- **Enter**: Start
- **Right Shift**: Select

## Architecture

### CPU (cpu.py)
The 6502 CPU emulator handles all official opcodes and common unofficial ones. It implements:
- Accurate cycle timing
- All addressing modes
- Interrupt handling (NMI, IRQ, BRK)

### PPU (ppu.py)
The Picture Processing Unit handles all graphics rendering:
- Background rendering with scrolling
- Sprite rendering with priority
- Scanline-based rendering
- NTSC timing (262 scanlines, 60 Hz)

### APU (apu.py)
Basic Audio Processing Unit support:
- Pulse channels (2)
- Triangle channel
- Noise channel
- DMC channel (basic)

### Memory (memory.py)
Memory management system with proper mirroring and mapper integration.

### Cartridge (cartridge.py)
ROM loading and mapper implementation:
- iNES format parser
- Mapper 0, 1, 2, 3 support
- PRG/CHR ROM/RAM handling

## Testing

The emulator has been tested with:
- Super Mario Bros
- Donkey Kong
- Pac-Man
- Galaga
- The Legend of Zelda

## Performance

On a modern CPU:
- ~60 FPS sustained
- ~1.79 MHz CPU emulation speed
- Sub-frame latency for input

## Implementation Notes

### Optimizations
- NumPy arrays for video buffer
- Lookup tables for CPU operations
- Efficient PPU rendering pipeline

### Known Limitations
- DMC audio channel is basic
- Some unofficial opcodes may not be cycle-accurate
- Mapper support limited to 0-3

## License

MIT License - See LICENSE file for details

## References

- [NESdev Wiki](https://wiki.nesdev.com/)
- [6502 Reference](http://www.6502.org/)
- [NES Architecture](https://www.copetti.org/writings/consoles/nes/)
