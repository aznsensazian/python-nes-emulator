#!/usr/bin/env python3
"""
Performance Benchmark for NES Emulator
Measures CPU and rendering performance
"""

import time
import sys
from cpu import CPU
from ppu import PPU
from memory import Memory
from nes import NES

class MockCartridge:
    """Mock cartridge for benchmarking"""
    def __init__(self):
        self.mirroring = 0
        self.prg_rom = bytearray(32768)
        self.chr_rom = bytearray(8192)
        
        # Fill with simple test program
        # Loop: INC $0200, JMP Loop
        self.prg_rom[0x0000] = 0xEE  # INC $0200
        self.prg_rom[0x0001] = 0x00
        self.prg_rom[0x0002] = 0x02
        self.prg_rom[0x0003] = 0x4C  # JMP $8000
        self.prg_rom[0x0004] = 0x00
        self.prg_rom[0x0005] = 0x80
        
        # Reset vector points to $8000
        self.prg_rom[0x7FFC] = 0x00
        self.prg_rom[0x7FFD] = 0x80
    
    def read(self, address):
        if address >= 0x8000:
            return self.prg_rom[address - 0x8000]
        return 0
    
    def write(self, address, value):
        pass
    
    def read_chr(self, address):
        return self.chr_rom[address & 0x1FFF]
    
    def write_chr(self, address, value):
        pass

def benchmark_cpu():
    """Benchmark CPU performance"""
    print("Benchmarking CPU...")
    
    mock_cart = MockCartridge()
    nes = NES(mock_cart)
    nes.reset()
    
    # Run for 1 million cycles
    target_cycles = 1_000_000
    start_time = time.time()
    
    while nes.cpu.total_cycles < target_cycles:
        nes.cpu.step()
    
    elapsed = time.time() - start_time
    cycles_per_second = target_cycles / elapsed
    mhz = cycles_per_second / 1_000_000
    
    print(f"  CPU Speed: {mhz:.2f} MHz")
    print(f"  Target: 1.79 MHz (NES CPU speed)")
    print(f"  Performance: {(mhz / 1.79) * 100:.1f}% of emulation time")
    print(f"  Cycles executed: {target_cycles:,}")
    print(f"  Time taken: {elapsed:.3f} seconds")
    
    return mhz

def benchmark_ppu():
    """Benchmark PPU performance"""
    print("\nBenchmarking PPU...")
    
    mock_cart = MockCartridge()
    nes = NES(mock_cart)
    nes.reset()
    
    # Render 60 frames
    frames = 60
    start_time = time.time()
    
    for _ in range(frames):
        nes.step_frame()
    
    elapsed = time.time() - start_time
    fps = frames / elapsed
    
    print(f"  Rendering Speed: {fps:.2f} FPS")
    print(f"  Target: 60 FPS")
    print(f"  Frame time: {(elapsed / frames) * 1000:.2f} ms")
    print(f"  Total time: {elapsed:.3f} seconds")
    
    return fps

def benchmark_full_system():
    """Benchmark complete emulator"""
    print("\nBenchmarking Full System...")
    
    mock_cart = MockCartridge()
    nes = NES(mock_cart)
    nes.reset()
    
    # Run for 1 second of emulated time (at 1.79 MHz)
    target_cycles = 1_789_773  # 1 second at NES CPU speed
    start_time = time.time()
    
    while nes.cpu.total_cycles < target_cycles:
        nes.step()
    
    elapsed = time.time() - start_time
    emulation_speed = 1.0 / elapsed
    
    print(f"  Emulation Speed: {emulation_speed:.2f}x realtime")
    print(f"  1 second of NES time = {elapsed:.3f} seconds real time")
    print(f"  CPU cycles: {nes.cpu.total_cycles:,}")
    print(f"  Frames rendered: {nes.ppu.frame}")
    
    return emulation_speed

def benchmark_memory():
    """Benchmark memory access"""
    print("\nBenchmarking Memory Access...")
    
    class MockNES:
        def __init__(self):
            self.ppu = type('obj', (object,), {
                'read_register': lambda self, addr: 0,
                'write_register': lambda self, addr, val: None
            })()
            self.apu = type('obj', (object,), {
                'read_register': lambda self, addr: 0,
                'write_register': lambda self, addr, val: None
            })()
            self.controller1 = type('obj', (object,), {
                'read': lambda self: 0,
                'write': lambda self, val: None
            })()
            self.controller2 = type('obj', (object,), {
                'read': lambda self: 0,
                'write': lambda self, val: None
            })()
            self.cartridge = MockCartridge()
    
    mock_nes = MockNES()
    memory = Memory(mock_nes)
    
    # Write 1 million bytes
    count = 1_000_000
    start_time = time.time()
    
    for i in range(count):
        memory.write(i & 0x07FF, i & 0xFF)
    
    write_time = time.time() - start_time
    
    # Read 1 million bytes
    start_time = time.time()
    
    for i in range(count):
        _ = memory.read(i & 0x07FF)
    
    read_time = time.time() - start_time
    
    print(f"  Write Speed: {count / write_time / 1_000_000:.2f} M ops/sec")
    print(f"  Read Speed: {count / read_time / 1_000_000:.2f} M ops/sec")
    print(f"  Write time: {write_time:.3f} seconds")
    print(f"  Read time: {read_time:.3f} seconds")

def main():
    print("="*60)
    print("NES Emulator Performance Benchmark")
    print("="*60)
    print()
    
    try:
        cpu_speed = benchmark_cpu()
        ppu_fps = benchmark_ppu()
        emulation_speed = benchmark_full_system()
        benchmark_memory()
        
        print()
        print("="*60)
        print("Summary")
        print("="*60)
        print(f"CPU Emulation: {cpu_speed:.2f} MHz ({(cpu_speed / 1.79) * 100:.1f}% of target)")
        print(f"PPU Rendering: {ppu_fps:.2f} FPS")
        print(f"Overall Speed: {emulation_speed:.2f}x realtime")
        print()
        
        if emulation_speed >= 1.0:
            print("✅ Emulator can run at full speed!")
        else:
            print("⚠️  Emulator is slower than realtime")
            print(f"   Need {1.0 / emulation_speed:.2f}x speedup for full speed")
        
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Benchmark error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
