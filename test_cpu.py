#!/usr/bin/env python3
"""
CPU Test Suite
Tests basic CPU functionality
"""

from cpu import CPU
from memory import Memory

class MockNES:
    """Mock NES for testing"""
    def __init__(self):
        self.memory = None

class MockMemory:
    """Simple memory for testing"""
    def __init__(self):
        self.ram = bytearray(0x10000)
    
    def read(self, address):
        return self.ram[address & 0xFFFF]
    
    def write(self, address, value):
        self.ram[address & 0xFFFF] = value & 0xFF

def test_cpu_basic():
    """Test basic CPU operations"""
    print("Testing CPU...")
    
    memory = MockMemory()
    cpu = CPU(memory)
    
    # Test LDA immediate
    memory.write(0x0000, 0xA9)  # LDA #$42
    memory.write(0x0001, 0x42)
    memory.write(0xFFFC, 0x00)  # Reset vector
    memory.write(0xFFFD, 0x00)
    
    cpu.reset()
    assert cpu.PC == 0x0000
    
    cpu.step()
    assert cpu.A == 0x42, f"Expected A=0x42, got A={cpu.A:02X}"
    assert cpu.get_flag(cpu.FLAG_Z) == 0, "Zero flag should be clear"
    assert cpu.get_flag(cpu.FLAG_N) == 0, "Negative flag should be clear"
    
    print("  ✓ LDA immediate")
    
    # Test ADC
    memory.write(0x0002, 0x69)  # ADC #$08
    memory.write(0x0003, 0x08)
    cpu.step()
    assert cpu.A == 0x4A, f"Expected A=0x4A, got A={cpu.A:02X}"
    
    print("  ✓ ADC")
    
    # Test flags
    memory.write(0x0004, 0xA9)  # LDA #$00
    memory.write(0x0005, 0x00)
    cpu.step()
    assert cpu.get_flag(cpu.FLAG_Z) == 1, "Zero flag should be set"
    
    print("  ✓ Zero flag")
    
    memory.write(0x0006, 0xA9)  # LDA #$FF
    memory.write(0x0007, 0xFF)
    cpu.step()
    assert cpu.get_flag(cpu.FLAG_N) == 1, "Negative flag should be set"
    
    print("  ✓ Negative flag")
    
    # Test stack operations
    memory.write(0x0008, 0x48)  # PHA
    cpu.A = 0x55
    old_sp = cpu.SP
    cpu.step()
    assert cpu.SP == (old_sp - 1) & 0xFF, "Stack pointer should decrement"
    assert memory.read(0x0100 + old_sp) == 0x55, "Value should be pushed"
    
    print("  ✓ Stack push")
    
    memory.write(0x0009, 0x68)  # PLA
    cpu.A = 0x00
    cpu.step()
    assert cpu.A == 0x55, "Value should be pulled from stack"
    
    print("  ✓ Stack pull")
    
    print("✅ CPU tests passed!\n")

def test_addressing_modes():
    """Test addressing modes"""
    print("Testing addressing modes...")
    
    memory = MockMemory()
    cpu = CPU(memory)
    
    # Zero page
    memory.write(0x0000, 0xA5)  # LDA $10
    memory.write(0x0001, 0x10)
    memory.write(0x0010, 0x33)
    memory.write(0xFFFC, 0x00)
    memory.write(0xFFFD, 0x00)
    
    cpu.reset()
    cpu.step()
    assert cpu.A == 0x33, f"Zero page: Expected A=0x33, got A={cpu.A:02X}"
    
    print("  ✓ Zero page")
    
    # Absolute
    memory.write(0x0002, 0xAD)  # LDA $1234
    memory.write(0x0003, 0x34)
    memory.write(0x0004, 0x12)
    memory.write(0x1234, 0x77)
    cpu.step()
    assert cpu.A == 0x77, f"Absolute: Expected A=0x77, got A={cpu.A:02X}"
    
    print("  ✓ Absolute")
    
    # Indexed
    memory.write(0x0005, 0xB5)  # LDA $10,X
    memory.write(0x0006, 0x10)
    cpu.X = 0x05
    memory.write(0x0015, 0x88)
    cpu.step()
    assert cpu.A == 0x88, f"Indexed: Expected A=0x88, got A={cpu.A:02X}"
    
    print("  ✓ Zero page indexed")
    
    print("✅ Addressing mode tests passed!\n")

def test_branches():
    """Test branch instructions"""
    print("Testing branch instructions...")
    
    memory = MockMemory()
    cpu = CPU(memory)
    
    memory.write(0xFFFC, 0x00)
    memory.write(0xFFFD, 0x00)
    
    # BEQ taken
    memory.write(0x0000, 0xA9)  # LDA #$00
    memory.write(0x0001, 0x00)
    memory.write(0x0002, 0xF0)  # BEQ $+5
    memory.write(0x0003, 0x03)
    
    cpu.reset()
    cpu.step()  # LDA
    old_pc = cpu.PC
    cpu.step()  # BEQ
    assert cpu.PC == old_pc + 3 + 2, "Branch should be taken"
    
    print("  ✓ BEQ taken")
    
    # BNE not taken
    memory.write(0x0007, 0xD0)  # BNE $+5
    memory.write(0x0008, 0x03)
    cpu.set_flag(cpu.FLAG_Z, 1)
    old_pc = cpu.PC
    cpu.step()
    assert cpu.PC == old_pc + 2, "Branch should not be taken"
    
    print("  ✓ BNE not taken")
    
    print("✅ Branch tests passed!\n")

if __name__ == "__main__":
    print("="*50)
    print("NES Emulator CPU Test Suite")
    print("="*50 + "\n")
    
    try:
        test_cpu_basic()
        test_addressing_modes()
        test_branches()
        
        print("="*50)
        print("All tests passed! ✅")
        print("="*50)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
