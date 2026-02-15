"""
6502 CPU Emulator for NES
Implements all official opcodes and common unofficial opcodes
"""

class CPU:
    def __init__(self, memory):
        self.memory = memory
        
        # Registers
        self.A = 0  # Accumulator
        self.X = 0  # X register
        self.Y = 0  # Y register
        self.PC = 0  # Program Counter
        self.SP = 0xFD  # Stack Pointer
        self.P = 0x24  # Status flags
        
        # Flags (positions in P register)
        self.FLAG_C = 0x01  # Carry
        self.FLAG_Z = 0x02  # Zero
        self.FLAG_I = 0x04  # Interrupt Disable
        self.FLAG_D = 0x08  # Decimal (not used on NES)
        self.FLAG_B = 0x10  # Break
        self.FLAG_U = 0x20  # Unused (always 1)
        self.FLAG_V = 0x40  # Overflow
        self.FLAG_N = 0x80  # Negative
        
        # Cycle counter
        self.cycles = 0
        self.total_cycles = 0
        
        # Interrupt flags
        self.nmi_pending = False
        self.irq_pending = False
        
        # Initialize opcode table
        self.init_opcodes()
    
    def reset(self):
        """Reset CPU to power-on state"""
        self.A = 0
        self.X = 0
        self.Y = 0
        self.SP = 0xFD
        self.P = 0x24
        # Read reset vector
        self.PC = self.read_word(0xFFFC)
        self.cycles = 0
        self.total_cycles = 7  # Reset takes 7 cycles
    
    def read(self, address):
        """Read byte from memory"""
        return self.memory.read(address & 0xFFFF)
    
    def write(self, address, value):
        """Write byte to memory"""
        self.memory.write(address & 0xFFFF, value & 0xFF)
    
    def read_word(self, address):
        """Read 16-bit word (little-endian)"""
        lo = self.read(address)
        hi = self.read(address + 1)
        return (hi << 8) | lo
    
    def read_word_bug(self, address):
        """Read word with 6502 page boundary bug"""
        lo = self.read(address)
        hi = self.read((address & 0xFF00) | ((address + 1) & 0x00FF))
        return (hi << 8) | lo
    
    # Stack operations
    def push(self, value):
        """Push byte to stack"""
        self.write(0x0100 + self.SP, value)
        self.SP = (self.SP - 1) & 0xFF
    
    def pull(self):
        """Pull byte from stack"""
        self.SP = (self.SP + 1) & 0xFF
        return self.read(0x0100 + self.SP)
    
    def push_word(self, value):
        """Push word to stack"""
        self.push((value >> 8) & 0xFF)
        self.push(value & 0xFF)
    
    def pull_word(self):
        """Pull word from stack"""
        lo = self.pull()
        hi = self.pull()
        return (hi << 8) | lo
    
    # Flag operations
    def get_flag(self, flag):
        """Get flag value"""
        return 1 if (self.P & flag) else 0
    
    def set_flag(self, flag, value):
        """Set flag value"""
        if value:
            self.P |= flag
        else:
            self.P &= ~flag
    
    def set_zn(self, value):
        """Set Zero and Negative flags based on value"""
        value &= 0xFF
        self.set_flag(self.FLAG_Z, value == 0)
        self.set_flag(self.FLAG_N, value & 0x80)
    
    # Addressing modes
    def addr_implied(self):
        return 0, 0
    
    def addr_accumulator(self):
        return 0, 0
    
    def addr_immediate(self):
        addr = self.PC
        self.PC += 1
        return addr, 0
    
    def addr_zero_page(self):
        addr = self.read(self.PC)
        self.PC += 1
        return addr, 0
    
    def addr_zero_page_x(self):
        addr = (self.read(self.PC) + self.X) & 0xFF
        self.PC += 1
        return addr, 0
    
    def addr_zero_page_y(self):
        addr = (self.read(self.PC) + self.Y) & 0xFF
        self.PC += 1
        return addr, 0
    
    def addr_absolute(self):
        addr = self.read_word(self.PC)
        self.PC += 2
        return addr, 0
    
    def addr_absolute_x(self):
        addr = self.read_word(self.PC)
        self.PC += 2
        page_crossed = ((addr & 0xFF00) != ((addr + self.X) & 0xFF00))
        return (addr + self.X) & 0xFFFF, (1 if page_crossed else 0)
    
    def addr_absolute_y(self):
        addr = self.read_word(self.PC)
        self.PC += 2
        page_crossed = ((addr & 0xFF00) != ((addr + self.Y) & 0xFF00))
        return (addr + self.Y) & 0xFFFF, (1 if page_crossed else 0)
    
    def addr_indirect(self):
        """JMP indirect with 6502 bug"""
        ptr = self.read_word(self.PC)
        self.PC += 2
        addr = self.read_word_bug(ptr)
        return addr, 0
    
    def addr_indexed_indirect(self):
        """(Indirect,X)"""
        ptr = (self.read(self.PC) + self.X) & 0xFF
        self.PC += 1
        addr = self.read_word(ptr)
        return addr, 0
    
    def addr_indirect_indexed(self):
        """(Indirect),Y"""
        ptr = self.read(self.PC)
        self.PC += 1
        addr = self.read_word(ptr)
        page_crossed = ((addr & 0xFF00) != ((addr + self.Y) & 0xFF00))
        return (addr + self.Y) & 0xFFFF, (1 if page_crossed else 0)
    
    def addr_relative(self):
        offset = self.read(self.PC)
        self.PC += 1
        if offset & 0x80:
            offset -= 0x100
        addr = (self.PC + offset) & 0xFFFF
        return addr, 0
    
    # Instructions
    def ADC(self, addr, page_crossed):
        """Add with Carry"""
        a = self.A
        b = self.read(addr)
        c = self.get_flag(self.FLAG_C)
        result = a + b + c
        
        self.A = result & 0xFF
        self.set_flag(self.FLAG_C, result > 0xFF)
        self.set_flag(self.FLAG_V, ((a ^ result) & (b ^ result) & 0x80) != 0)
        self.set_zn(self.A)
        return 1 + page_crossed
    
    def AND(self, addr, page_crossed):
        """Logical AND"""
        self.A &= self.read(addr)
        self.set_zn(self.A)
        return 1 + page_crossed
    
    def ASL_ACC(self, addr, page_crossed):
        """Arithmetic Shift Left (Accumulator)"""
        self.set_flag(self.FLAG_C, self.A & 0x80)
        self.A = (self.A << 1) & 0xFF
        self.set_zn(self.A)
        return 0
    
    def ASL(self, addr, page_crossed):
        """Arithmetic Shift Left"""
        value = self.read(addr)
        self.set_flag(self.FLAG_C, value & 0x80)
        value = (value << 1) & 0xFF
        self.write(addr, value)
        self.set_zn(value)
        return 0
    
    def BCC(self, addr, page_crossed):
        """Branch if Carry Clear"""
        if not self.get_flag(self.FLAG_C):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def BCS(self, addr, page_crossed):
        """Branch if Carry Set"""
        if self.get_flag(self.FLAG_C):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def BEQ(self, addr, page_crossed):
        """Branch if Equal"""
        if self.get_flag(self.FLAG_Z):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def BIT(self, addr, page_crossed):
        """Bit Test"""
        value = self.read(addr)
        self.set_flag(self.FLAG_V, value & 0x40)
        self.set_flag(self.FLAG_N, value & 0x80)
        self.set_flag(self.FLAG_Z, (value & self.A) == 0)
        return 0
    
    def BMI(self, addr, page_crossed):
        """Branch if Minus"""
        if self.get_flag(self.FLAG_N):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def BNE(self, addr, page_crossed):
        """Branch if Not Equal"""
        if not self.get_flag(self.FLAG_Z):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def BPL(self, addr, page_crossed):
        """Branch if Positive"""
        if not self.get_flag(self.FLAG_N):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def BRK(self, addr, page_crossed):
        """Force Interrupt"""
        self.PC += 1
        self.push_word(self.PC)
        self.push(self.P | self.FLAG_B | self.FLAG_U)
        self.set_flag(self.FLAG_I, 1)
        self.PC = self.read_word(0xFFFE)
        return 0
    
    def BVC(self, addr, page_crossed):
        """Branch if Overflow Clear"""
        if not self.get_flag(self.FLAG_V):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def BVS(self, addr, page_crossed):
        """Branch if Overflow Set"""
        if self.get_flag(self.FLAG_V):
            self.cycles += 1
            if (self.PC & 0xFF00) != (addr & 0xFF00):
                self.cycles += 1
            self.PC = addr
        return 0
    
    def CLC(self, addr, page_crossed):
        """Clear Carry Flag"""
        self.set_flag(self.FLAG_C, 0)
        return 0
    
    def CLD(self, addr, page_crossed):
        """Clear Decimal Flag"""
        self.set_flag(self.FLAG_D, 0)
        return 0
    
    def CLI(self, addr, page_crossed):
        """Clear Interrupt Disable"""
        self.set_flag(self.FLAG_I, 0)
        return 0
    
    def CLV(self, addr, page_crossed):
        """Clear Overflow Flag"""
        self.set_flag(self.FLAG_V, 0)
        return 0
    
    def CMP(self, addr, page_crossed):
        """Compare Accumulator"""
        value = self.read(addr)
        result = self.A - value
        self.set_flag(self.FLAG_C, self.A >= value)
        self.set_zn(result)
        return 1 + page_crossed
    
    def CPX(self, addr, page_crossed):
        """Compare X Register"""
        value = self.read(addr)
        result = self.X - value
        self.set_flag(self.FLAG_C, self.X >= value)
        self.set_zn(result)
        return 0
    
    def CPY(self, addr, page_crossed):
        """Compare Y Register"""
        value = self.read(addr)
        result = self.Y - value
        self.set_flag(self.FLAG_C, self.Y >= value)
        self.set_zn(result)
        return 0
    
    def DEC(self, addr, page_crossed):
        """Decrement Memory"""
        value = (self.read(addr) - 1) & 0xFF
        self.write(addr, value)
        self.set_zn(value)
        return 0
    
    def DEX(self, addr, page_crossed):
        """Decrement X"""
        self.X = (self.X - 1) & 0xFF
        self.set_zn(self.X)
        return 0
    
    def DEY(self, addr, page_crossed):
        """Decrement Y"""
        self.Y = (self.Y - 1) & 0xFF
        self.set_zn(self.Y)
        return 0
    
    def EOR(self, addr, page_crossed):
        """Exclusive OR"""
        self.A ^= self.read(addr)
        self.set_zn(self.A)
        return 1 + page_crossed
    
    def INC(self, addr, page_crossed):
        """Increment Memory"""
        value = (self.read(addr) + 1) & 0xFF
        self.write(addr, value)
        self.set_zn(value)
        return 0
    
    def INX(self, addr, page_crossed):
        """Increment X"""
        self.X = (self.X + 1) & 0xFF
        self.set_zn(self.X)
        return 0
    
    def INY(self, addr, page_crossed):
        """Increment Y"""
        self.Y = (self.Y + 1) & 0xFF
        self.set_zn(self.Y)
        return 0
    
    def JMP(self, addr, page_crossed):
        """Jump"""
        self.PC = addr
        return 0
    
    def JSR(self, addr, page_crossed):
        """Jump to Subroutine"""
        self.push_word(self.PC - 1)
        self.PC = addr
        return 0
    
    def LDA(self, addr, page_crossed):
        """Load Accumulator"""
        self.A = self.read(addr)
        self.set_zn(self.A)
        return 1 + page_crossed
    
    def LDX(self, addr, page_crossed):
        """Load X Register"""
        self.X = self.read(addr)
        self.set_zn(self.X)
        return 1 + page_crossed
    
    def LDY(self, addr, page_crossed):
        """Load Y Register"""
        self.Y = self.read(addr)
        self.set_zn(self.Y)
        return 1 + page_crossed
    
    def LSR_ACC(self, addr, page_crossed):
        """Logical Shift Right (Accumulator)"""
        self.set_flag(self.FLAG_C, self.A & 0x01)
        self.A >>= 1
        self.set_zn(self.A)
        return 0
    
    def LSR(self, addr, page_crossed):
        """Logical Shift Right"""
        value = self.read(addr)
        self.set_flag(self.FLAG_C, value & 0x01)
        value >>= 1
        self.write(addr, value)
        self.set_zn(value)
        return 0
    
    def NOP(self, addr, page_crossed):
        """No Operation"""
        return 1 + page_crossed
    
    def ORA(self, addr, page_crossed):
        """Logical OR"""
        self.A |= self.read(addr)
        self.set_zn(self.A)
        return 1 + page_crossed
    
    def PHA(self, addr, page_crossed):
        """Push Accumulator"""
        self.push(self.A)
        return 0
    
    def PHP(self, addr, page_crossed):
        """Push Processor Status"""
        self.push(self.P | self.FLAG_B | self.FLAG_U)
        return 0
    
    def PLA(self, addr, page_crossed):
        """Pull Accumulator"""
        self.A = self.pull()
        self.set_zn(self.A)
        return 0
    
    def PLP(self, addr, page_crossed):
        """Pull Processor Status"""
        self.P = (self.pull() & 0xEF) | self.FLAG_U
        return 0
    
    def ROL_ACC(self, addr, page_crossed):
        """Rotate Left (Accumulator)"""
        carry = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, self.A & 0x80)
        self.A = ((self.A << 1) | carry) & 0xFF
        self.set_zn(self.A)
        return 0
    
    def ROL(self, addr, page_crossed):
        """Rotate Left"""
        value = self.read(addr)
        carry = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, value & 0x80)
        value = ((value << 1) | carry) & 0xFF
        self.write(addr, value)
        self.set_zn(value)
        return 0
    
    def ROR_ACC(self, addr, page_crossed):
        """Rotate Right (Accumulator)"""
        carry = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, self.A & 0x01)
        self.A = (self.A >> 1) | (carry << 7)
        self.set_zn(self.A)
        return 0
    
    def ROR(self, addr, page_crossed):
        """Rotate Right"""
        value = self.read(addr)
        carry = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, value & 0x01)
        value = (value >> 1) | (carry << 7)
        self.write(addr, value)
        self.set_zn(value)
        return 0
    
    def RTI(self, addr, page_crossed):
        """Return from Interrupt"""
        self.P = (self.pull() & 0xEF) | self.FLAG_U
        self.PC = self.pull_word()
        return 0
    
    def RTS(self, addr, page_crossed):
        """Return from Subroutine"""
        self.PC = self.pull_word() + 1
        return 0
    
    def SBC(self, addr, page_crossed):
        """Subtract with Carry"""
        a = self.A
        b = self.read(addr)
        c = self.get_flag(self.FLAG_C)
        result = a - b - (1 - c)
        
        self.A = result & 0xFF
        self.set_flag(self.FLAG_C, result >= 0)
        self.set_flag(self.FLAG_V, ((a ^ b) & (a ^ result) & 0x80) != 0)
        self.set_zn(self.A)
        return 1 + page_crossed
    
    def SEC(self, addr, page_crossed):
        """Set Carry Flag"""
        self.set_flag(self.FLAG_C, 1)
        return 0
    
    def SED(self, addr, page_crossed):
        """Set Decimal Flag"""
        self.set_flag(self.FLAG_D, 1)
        return 0
    
    def SEI(self, addr, page_crossed):
        """Set Interrupt Disable"""
        self.set_flag(self.FLAG_I, 1)
        return 0
    
    def STA(self, addr, page_crossed):
        """Store Accumulator"""
        self.write(addr, self.A)
        return 0
    
    def STX(self, addr, page_crossed):
        """Store X Register"""
        self.write(addr, self.X)
        return 0
    
    def STY(self, addr, page_crossed):
        """Store Y Register"""
        self.write(addr, self.Y)
        return 0
    
    def TAX(self, addr, page_crossed):
        """Transfer A to X"""
        self.X = self.A
        self.set_zn(self.X)
        return 0
    
    def TAY(self, addr, page_crossed):
        """Transfer A to Y"""
        self.Y = self.A
        self.set_zn(self.Y)
        return 0
    
    def TSX(self, addr, page_crossed):
        """Transfer Stack Pointer to X"""
        self.X = self.SP
        self.set_zn(self.X)
        return 0
    
    def TXA(self, addr, page_crossed):
        """Transfer X to A"""
        self.A = self.X
        self.set_zn(self.A)
        return 0
    
    def TXS(self, addr, page_crossed):
        """Transfer X to Stack Pointer"""
        self.SP = self.X
        return 0
    
    def TYA(self, addr, page_crossed):
        """Transfer Y to A"""
        self.A = self.Y
        self.set_zn(self.A)
        return 0
    
    # Unofficial opcodes
    def LAX(self, addr, page_crossed):
        """Load A and X"""
        value = self.read(addr)
        self.A = value
        self.X = value
        self.set_zn(value)
        return 1 + page_crossed
    
    def SAX(self, addr, page_crossed):
        """Store A AND X"""
        self.write(addr, self.A & self.X)
        return 0
    
    def DCP(self, addr, page_crossed):
        """Decrement and Compare"""
        value = (self.read(addr) - 1) & 0xFF
        self.write(addr, value)
        result = self.A - value
        self.set_flag(self.FLAG_C, self.A >= value)
        self.set_zn(result)
        return 0
    
    def ISC(self, addr, page_crossed):
        """Increment and Subtract"""
        value = (self.read(addr) + 1) & 0xFF
        self.write(addr, value)
        # SBC
        a = self.A
        b = value
        c = self.get_flag(self.FLAG_C)
        result = a - b - (1 - c)
        self.A = result & 0xFF
        self.set_flag(self.FLAG_C, result >= 0)
        self.set_flag(self.FLAG_V, ((a ^ b) & (a ^ result) & 0x80) != 0)
        self.set_zn(self.A)
        return 0
    
    def SLO(self, addr, page_crossed):
        """Shift Left and OR"""
        value = self.read(addr)
        self.set_flag(self.FLAG_C, value & 0x80)
        value = (value << 1) & 0xFF
        self.write(addr, value)
        self.A |= value
        self.set_zn(self.A)
        return 0
    
    def RLA(self, addr, page_crossed):
        """Rotate Left and AND"""
        value = self.read(addr)
        carry = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, value & 0x80)
        value = ((value << 1) | carry) & 0xFF
        self.write(addr, value)
        self.A &= value
        self.set_zn(self.A)
        return 0
    
    def SRE(self, addr, page_crossed):
        """Shift Right and EOR"""
        value = self.read(addr)
        self.set_flag(self.FLAG_C, value & 0x01)
        value >>= 1
        self.write(addr, value)
        self.A ^= value
        self.set_zn(self.A)
        return 0
    
    def RRA(self, addr, page_crossed):
        """Rotate Right and Add"""
        value = self.read(addr)
        carry = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, value & 0x01)
        value = (value >> 1) | (carry << 7)
        self.write(addr, value)
        # ADC
        a = self.A
        b = value
        c = self.get_flag(self.FLAG_C)
        result = a + b + c
        self.A = result & 0xFF
        self.set_flag(self.FLAG_C, result > 0xFF)
        self.set_flag(self.FLAG_V, ((a ^ result) & (b ^ result) & 0x80) != 0)
        self.set_zn(self.A)
        return 0
    
    def init_opcodes(self):
        """Initialize opcode lookup table"""
        self.opcodes = [None] * 256
        
        # Official opcodes
        # ADC
        self.opcodes[0x69] = (self.ADC, self.addr_immediate, 2)
        self.opcodes[0x65] = (self.ADC, self.addr_zero_page, 3)
        self.opcodes[0x75] = (self.ADC, self.addr_zero_page_x, 4)
        self.opcodes[0x6D] = (self.ADC, self.addr_absolute, 4)
        self.opcodes[0x7D] = (self.ADC, self.addr_absolute_x, 4)
        self.opcodes[0x79] = (self.ADC, self.addr_absolute_y, 4)
        self.opcodes[0x61] = (self.ADC, self.addr_indexed_indirect, 6)
        self.opcodes[0x71] = (self.ADC, self.addr_indirect_indexed, 5)
        
        # AND
        self.opcodes[0x29] = (self.AND, self.addr_immediate, 2)
        self.opcodes[0x25] = (self.AND, self.addr_zero_page, 3)
        self.opcodes[0x35] = (self.AND, self.addr_zero_page_x, 4)
        self.opcodes[0x2D] = (self.AND, self.addr_absolute, 4)
        self.opcodes[0x3D] = (self.AND, self.addr_absolute_x, 4)
        self.opcodes[0x39] = (self.AND, self.addr_absolute_y, 4)
        self.opcodes[0x21] = (self.AND, self.addr_indexed_indirect, 6)
        self.opcodes[0x31] = (self.AND, self.addr_indirect_indexed, 5)
        
        # ASL
        self.opcodes[0x0A] = (self.ASL_ACC, self.addr_accumulator, 2)
        self.opcodes[0x06] = (self.ASL, self.addr_zero_page, 5)
        self.opcodes[0x16] = (self.ASL, self.addr_zero_page_x, 6)
        self.opcodes[0x0E] = (self.ASL, self.addr_absolute, 6)
        self.opcodes[0x1E] = (self.ASL, self.addr_absolute_x, 7)
        
        # Branch instructions
        self.opcodes[0x90] = (self.BCC, self.addr_relative, 2)
        self.opcodes[0xB0] = (self.BCS, self.addr_relative, 2)
        self.opcodes[0xF0] = (self.BEQ, self.addr_relative, 2)
        self.opcodes[0x30] = (self.BMI, self.addr_relative, 2)
        self.opcodes[0xD0] = (self.BNE, self.addr_relative, 2)
        self.opcodes[0x10] = (self.BPL, self.addr_relative, 2)
        self.opcodes[0x50] = (self.BVC, self.addr_relative, 2)
        self.opcodes[0x70] = (self.BVS, self.addr_relative, 2)
        
        # BIT
        self.opcodes[0x24] = (self.BIT, self.addr_zero_page, 3)
        self.opcodes[0x2C] = (self.BIT, self.addr_absolute, 4)
        
        # BRK
        self.opcodes[0x00] = (self.BRK, self.addr_implied, 7)
        
        # CMP
        self.opcodes[0xC9] = (self.CMP, self.addr_immediate, 2)
        self.opcodes[0xC5] = (self.CMP, self.addr_zero_page, 3)
        self.opcodes[0xD5] = (self.CMP, self.addr_zero_page_x, 4)
        self.opcodes[0xCD] = (self.CMP, self.addr_absolute, 4)
        self.opcodes[0xDD] = (self.CMP, self.addr_absolute_x, 4)
        self.opcodes[0xD9] = (self.CMP, self.addr_absolute_y, 4)
        self.opcodes[0xC1] = (self.CMP, self.addr_indexed_indirect, 6)
        self.opcodes[0xD1] = (self.CMP, self.addr_indirect_indexed, 5)
        
        # CPX
        self.opcodes[0xE0] = (self.CPX, self.addr_immediate, 2)
        self.opcodes[0xE4] = (self.CPX, self.addr_zero_page, 3)
        self.opcodes[0xEC] = (self.CPX, self.addr_absolute, 4)
        
        # CPY
        self.opcodes[0xC0] = (self.CPY, self.addr_immediate, 2)
        self.opcodes[0xC4] = (self.CPY, self.addr_zero_page, 3)
        self.opcodes[0xCC] = (self.CPY, self.addr_absolute, 4)
        
        # DEC
        self.opcodes[0xC6] = (self.DEC, self.addr_zero_page, 5)
        self.opcodes[0xD6] = (self.DEC, self.addr_zero_page_x, 6)
        self.opcodes[0xCE] = (self.DEC, self.addr_absolute, 6)
        self.opcodes[0xDE] = (self.DEC, self.addr_absolute_x, 7)
        
        # DEX, DEY
        self.opcodes[0xCA] = (self.DEX, self.addr_implied, 2)
        self.opcodes[0x88] = (self.DEY, self.addr_implied, 2)
        
        # EOR
        self.opcodes[0x49] = (self.EOR, self.addr_immediate, 2)
        self.opcodes[0x45] = (self.EOR, self.addr_zero_page, 3)
        self.opcodes[0x55] = (self.EOR, self.addr_zero_page_x, 4)
        self.opcodes[0x4D] = (self.EOR, self.addr_absolute, 4)
        self.opcodes[0x5D] = (self.EOR, self.addr_absolute_x, 4)
        self.opcodes[0x59] = (self.EOR, self.addr_absolute_y, 4)
        self.opcodes[0x41] = (self.EOR, self.addr_indexed_indirect, 6)
        self.opcodes[0x51] = (self.EOR, self.addr_indirect_indexed, 5)
        
        # Flag instructions
        self.opcodes[0x18] = (self.CLC, self.addr_implied, 2)
        self.opcodes[0xD8] = (self.CLD, self.addr_implied, 2)
        self.opcodes[0x58] = (self.CLI, self.addr_implied, 2)
        self.opcodes[0xB8] = (self.CLV, self.addr_implied, 2)
        self.opcodes[0x38] = (self.SEC, self.addr_implied, 2)
        self.opcodes[0xF8] = (self.SED, self.addr_implied, 2)
        self.opcodes[0x78] = (self.SEI, self.addr_implied, 2)
        
        # INC
        self.opcodes[0xE6] = (self.INC, self.addr_zero_page, 5)
        self.opcodes[0xF6] = (self.INC, self.addr_zero_page_x, 6)
        self.opcodes[0xEE] = (self.INC, self.addr_absolute, 6)
        self.opcodes[0xFE] = (self.INC, self.addr_absolute_x, 7)
        
        # INX, INY
        self.opcodes[0xE8] = (self.INX, self.addr_implied, 2)
        self.opcodes[0xC8] = (self.INY, self.addr_implied, 2)
        
        # JMP
        self.opcodes[0x4C] = (self.JMP, self.addr_absolute, 3)
        self.opcodes[0x6C] = (self.JMP, self.addr_indirect, 5)
        
        # JSR
        self.opcodes[0x20] = (self.JSR, self.addr_absolute, 6)
        
        # LDA
        self.opcodes[0xA9] = (self.LDA, self.addr_immediate, 2)
        self.opcodes[0xA5] = (self.LDA, self.addr_zero_page, 3)
        self.opcodes[0xB5] = (self.LDA, self.addr_zero_page_x, 4)
        self.opcodes[0xAD] = (self.LDA, self.addr_absolute, 4)
        self.opcodes[0xBD] = (self.LDA, self.addr_absolute_x, 4)
        self.opcodes[0xB9] = (self.LDA, self.addr_absolute_y, 4)
        self.opcodes[0xA1] = (self.LDA, self.addr_indexed_indirect, 6)
        self.opcodes[0xB1] = (self.LDA, self.addr_indirect_indexed, 5)
        
        # LDX
        self.opcodes[0xA2] = (self.LDX, self.addr_immediate, 2)
        self.opcodes[0xA6] = (self.LDX, self.addr_zero_page, 3)
        self.opcodes[0xB6] = (self.LDX, self.addr_zero_page_y, 4)
        self.opcodes[0xAE] = (self.LDX, self.addr_absolute, 4)
        self.opcodes[0xBE] = (self.LDX, self.addr_absolute_y, 4)
        
        # LDY
        self.opcodes[0xA0] = (self.LDY, self.addr_immediate, 2)
        self.opcodes[0xA4] = (self.LDY, self.addr_zero_page, 3)
        self.opcodes[0xB4] = (self.LDY, self.addr_zero_page_x, 4)
        self.opcodes[0xAC] = (self.LDY, self.addr_absolute, 4)
        self.opcodes[0xBC] = (self.LDY, self.addr_absolute_x, 4)
        
        # LSR
        self.opcodes[0x4A] = (self.LSR_ACC, self.addr_accumulator, 2)
        self.opcodes[0x46] = (self.LSR, self.addr_zero_page, 5)
        self.opcodes[0x56] = (self.LSR, self.addr_zero_page_x, 6)
        self.opcodes[0x4E] = (self.LSR, self.addr_absolute, 6)
        self.opcodes[0x5E] = (self.LSR, self.addr_absolute_x, 7)
        
        # NOP
        self.opcodes[0xEA] = (self.NOP, self.addr_implied, 2)
        
        # ORA
        self.opcodes[0x09] = (self.ORA, self.addr_immediate, 2)
        self.opcodes[0x05] = (self.ORA, self.addr_zero_page, 3)
        self.opcodes[0x15] = (self.ORA, self.addr_zero_page_x, 4)
        self.opcodes[0x0D] = (self.ORA, self.addr_absolute, 4)
        self.opcodes[0x1D] = (self.ORA, self.addr_absolute_x, 4)
        self.opcodes[0x19] = (self.ORA, self.addr_absolute_y, 4)
        self.opcodes[0x01] = (self.ORA, self.addr_indexed_indirect, 6)
        self.opcodes[0x11] = (self.ORA, self.addr_indirect_indexed, 5)
        
        # Stack operations
        self.opcodes[0x48] = (self.PHA, self.addr_implied, 3)
        self.opcodes[0x08] = (self.PHP, self.addr_implied, 3)
        self.opcodes[0x68] = (self.PLA, self.addr_implied, 4)
        self.opcodes[0x28] = (self.PLP, self.addr_implied, 4)
        
        # ROL
        self.opcodes[0x2A] = (self.ROL_ACC, self.addr_accumulator, 2)
        self.opcodes[0x26] = (self.ROL, self.addr_zero_page, 5)
        self.opcodes[0x36] = (self.ROL, self.addr_zero_page_x, 6)
        self.opcodes[0x2E] = (self.ROL, self.addr_absolute, 6)
        self.opcodes[0x3E] = (self.ROL, self.addr_absolute_x, 7)
        
        # ROR
        self.opcodes[0x6A] = (self.ROR_ACC, self.addr_accumulator, 2)
        self.opcodes[0x66] = (self.ROR, self.addr_zero_page, 5)
        self.opcodes[0x76] = (self.ROR, self.addr_zero_page_x, 6)
        self.opcodes[0x6E] = (self.ROR, self.addr_absolute, 6)
        self.opcodes[0x7E] = (self.ROR, self.addr_absolute_x, 7)
        
        # RTI, RTS
        self.opcodes[0x40] = (self.RTI, self.addr_implied, 6)
        self.opcodes[0x60] = (self.RTS, self.addr_implied, 6)
        
        # SBC
        self.opcodes[0xE9] = (self.SBC, self.addr_immediate, 2)
        self.opcodes[0xE5] = (self.SBC, self.addr_zero_page, 3)
        self.opcodes[0xF5] = (self.SBC, self.addr_zero_page_x, 4)
        self.opcodes[0xED] = (self.SBC, self.addr_absolute, 4)
        self.opcodes[0xFD] = (self.SBC, self.addr_absolute_x, 4)
        self.opcodes[0xF9] = (self.SBC, self.addr_absolute_y, 4)
        self.opcodes[0xE1] = (self.SBC, self.addr_indexed_indirect, 6)
        self.opcodes[0xF1] = (self.SBC, self.addr_indirect_indexed, 5)
        
        # STA
        self.opcodes[0x85] = (self.STA, self.addr_zero_page, 3)
        self.opcodes[0x95] = (self.STA, self.addr_zero_page_x, 4)
        self.opcodes[0x8D] = (self.STA, self.addr_absolute, 4)
        self.opcodes[0x9D] = (self.STA, self.addr_absolute_x, 5)
        self.opcodes[0x99] = (self.STA, self.addr_absolute_y, 5)
        self.opcodes[0x81] = (self.STA, self.addr_indexed_indirect, 6)
        self.opcodes[0x91] = (self.STA, self.addr_indirect_indexed, 6)
        
        # STX
        self.opcodes[0x86] = (self.STX, self.addr_zero_page, 3)
        self.opcodes[0x96] = (self.STX, self.addr_zero_page_y, 4)
        self.opcodes[0x8E] = (self.STX, self.addr_absolute, 4)
        
        # STY
        self.opcodes[0x84] = (self.STY, self.addr_zero_page, 3)
        self.opcodes[0x94] = (self.STY, self.addr_zero_page_x, 4)
        self.opcodes[0x8C] = (self.STY, self.addr_absolute, 4)
        
        # Transfer instructions
        self.opcodes[0xAA] = (self.TAX, self.addr_implied, 2)
        self.opcodes[0xA8] = (self.TAY, self.addr_implied, 2)
        self.opcodes[0xBA] = (self.TSX, self.addr_implied, 2)
        self.opcodes[0x8A] = (self.TXA, self.addr_implied, 2)
        self.opcodes[0x9A] = (self.TXS, self.addr_implied, 2)
        self.opcodes[0x98] = (self.TYA, self.addr_implied, 2)
        
        # Unofficial opcodes
        # LAX
        self.opcodes[0xA7] = (self.LAX, self.addr_zero_page, 3)
        self.opcodes[0xB7] = (self.LAX, self.addr_zero_page_y, 4)
        self.opcodes[0xAF] = (self.LAX, self.addr_absolute, 4)
        self.opcodes[0xBF] = (self.LAX, self.addr_absolute_y, 4)
        self.opcodes[0xA3] = (self.LAX, self.addr_indexed_indirect, 6)
        self.opcodes[0xB3] = (self.LAX, self.addr_indirect_indexed, 5)
        
        # SAX
        self.opcodes[0x87] = (self.SAX, self.addr_zero_page, 3)
        self.opcodes[0x97] = (self.SAX, self.addr_zero_page_y, 4)
        self.opcodes[0x8F] = (self.SAX, self.addr_absolute, 4)
        self.opcodes[0x83] = (self.SAX, self.addr_indexed_indirect, 6)
        
        # DCP
        self.opcodes[0xC7] = (self.DCP, self.addr_zero_page, 5)
        self.opcodes[0xD7] = (self.DCP, self.addr_zero_page_x, 6)
        self.opcodes[0xCF] = (self.DCP, self.addr_absolute, 6)
        self.opcodes[0xDF] = (self.DCP, self.addr_absolute_x, 7)
        self.opcodes[0xDB] = (self.DCP, self.addr_absolute_y, 7)
        self.opcodes[0xC3] = (self.DCP, self.addr_indexed_indirect, 8)
        self.opcodes[0xD3] = (self.DCP, self.addr_indirect_indexed, 8)
        
        # ISC
        self.opcodes[0xE7] = (self.ISC, self.addr_zero_page, 5)
        self.opcodes[0xF7] = (self.ISC, self.addr_zero_page_x, 6)
        self.opcodes[0xEF] = (self.ISC, self.addr_absolute, 6)
        self.opcodes[0xFF] = (self.ISC, self.addr_absolute_x, 7)
        self.opcodes[0xFB] = (self.ISC, self.addr_absolute_y, 7)
        self.opcodes[0xE3] = (self.ISC, self.addr_indexed_indirect, 8)
        self.opcodes[0xF3] = (self.ISC, self.addr_indirect_indexed, 8)
        
        # SLO
        self.opcodes[0x07] = (self.SLO, self.addr_zero_page, 5)
        self.opcodes[0x17] = (self.SLO, self.addr_zero_page_x, 6)
        self.opcodes[0x0F] = (self.SLO, self.addr_absolute, 6)
        self.opcodes[0x1F] = (self.SLO, self.addr_absolute_x, 7)
        self.opcodes[0x1B] = (self.SLO, self.addr_absolute_y, 7)
        self.opcodes[0x03] = (self.SLO, self.addr_indexed_indirect, 8)
        self.opcodes[0x13] = (self.SLO, self.addr_indirect_indexed, 8)
        
        # RLA
        self.opcodes[0x27] = (self.RLA, self.addr_zero_page, 5)
        self.opcodes[0x37] = (self.RLA, self.addr_zero_page_x, 6)
        self.opcodes[0x2F] = (self.RLA, self.addr_absolute, 6)
        self.opcodes[0x3F] = (self.RLA, self.addr_absolute_x, 7)
        self.opcodes[0x3B] = (self.RLA, self.addr_absolute_y, 7)
        self.opcodes[0x23] = (self.RLA, self.addr_indexed_indirect, 8)
        self.opcodes[0x33] = (self.RLA, self.addr_indirect_indexed, 8)
        
        # SRE
        self.opcodes[0x47] = (self.SRE, self.addr_zero_page, 5)
        self.opcodes[0x57] = (self.SRE, self.addr_zero_page_x, 6)
        self.opcodes[0x4F] = (self.SRE, self.addr_absolute, 6)
        self.opcodes[0x5F] = (self.SRE, self.addr_absolute_x, 7)
        self.opcodes[0x5B] = (self.SRE, self.addr_absolute_y, 7)
        self.opcodes[0x43] = (self.SRE, self.addr_indexed_indirect, 8)
        self.opcodes[0x53] = (self.SRE, self.addr_indirect_indexed, 8)
        
        # RRA
        self.opcodes[0x67] = (self.RRA, self.addr_zero_page, 5)
        self.opcodes[0x77] = (self.RRA, self.addr_zero_page_x, 6)
        self.opcodes[0x6F] = (self.RRA, self.addr_absolute, 6)
        self.opcodes[0x7F] = (self.RRA, self.addr_absolute_x, 7)
        self.opcodes[0x7B] = (self.RRA, self.addr_absolute_y, 7)
        self.opcodes[0x63] = (self.RRA, self.addr_indexed_indirect, 8)
        self.opcodes[0x73] = (self.RRA, self.addr_indirect_indexed, 8)
        
        # Unofficial NOPs
        nop_opcodes = [0x1A, 0x3A, 0x5A, 0x7A, 0xDA, 0xFA]
        for opcode in nop_opcodes:
            self.opcodes[opcode] = (self.NOP, self.addr_implied, 2)
        
        # DOP (double NOP)
        dop_opcodes = [0x04, 0x14, 0x34, 0x44, 0x54, 0x64, 0x74, 0x80, 0x82, 0x89, 0xC2, 0xD4, 0xE2, 0xF4]
        for opcode in dop_opcodes:
            self.opcodes[opcode] = (self.NOP, self.addr_immediate, 2)
        
        # TOP (triple NOP)
        top_opcodes = [0x0C, 0x1C, 0x3C, 0x5C, 0x7C, 0xDC, 0xFC]
        for opcode in top_opcodes:
            self.opcodes[opcode] = (self.NOP, self.addr_absolute_x, 4)
    
    def step(self):
        """Execute one instruction"""
        if self.nmi_pending:
            self.nmi()
            self.nmi_pending = False
        elif self.irq_pending and not self.get_flag(self.FLAG_I):
            self.irq()
            self.irq_pending = False
        
        opcode = self.read(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        
        if self.opcodes[opcode] is None:
            # Unimplemented opcode
            print(f"Unimplemented opcode: ${opcode:02X} at ${self.PC-1:04X}")
            return 2
        
        instruction, addr_mode, cycles = self.opcodes[opcode]
        addr, page_crossed = addr_mode()
        extra_cycles = instruction(addr, page_crossed)
        
        self.cycles = cycles + extra_cycles
        self.total_cycles += self.cycles
        return self.cycles
    
    def nmi(self):
        """Non-Maskable Interrupt"""
        self.push_word(self.PC)
        self.push(self.P & ~self.FLAG_B | self.FLAG_U)
        self.set_flag(self.FLAG_I, 1)
        self.PC = self.read_word(0xFFFA)
        self.cycles = 7
    
    def irq(self):
        """Interrupt Request"""
        self.push_word(self.PC)
        self.push(self.P & ~self.FLAG_B | self.FLAG_U)
        self.set_flag(self.FLAG_I, 1)
        self.PC = self.read_word(0xFFFE)
        self.cycles = 7
    
    def trigger_nmi(self):
        """Trigger NMI"""
        self.nmi_pending = True
    
    def trigger_irq(self):
        """Trigger IRQ"""
        self.irq_pending = True
