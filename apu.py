"""
NES APU (Audio Processing Unit)
Basic implementation of audio channels
"""

import numpy as np

class APU:
    def __init__(self, nes):
        self.nes = nes
        
        # Pulse channels
        self.pulse1 = PulseChannel()
        self.pulse2 = PulseChannel()
        
        # Triangle channel
        self.triangle = TriangleChannel()
        
        # Noise channel
        self.noise = NoiseChannel()
        
        # DMC channel
        self.dmc = DMCChannel()
        
        # Frame counter
        self.frame_counter = 0
        self.frame_mode = 0  # 0 = 4-step, 1 = 5-step
        self.frame_irq = False
        
        # Cycle counter
        self.cycles = 0
        
        # Audio buffer
        self.sample_rate = 44100
        self.buffer = []
    
    def reset(self):
        """Reset APU"""
        self.pulse1.reset()
        self.pulse2.reset()
        self.triangle.reset()
        self.noise.reset()
        self.dmc.reset()
        self.frame_counter = 0
        self.frame_mode = 0
        self.frame_irq = False
        self.cycles = 0
        self.buffer = []
    
    def read_register(self, address):
        """Read from APU register"""
        if address == 0x4015:  # Status
            value = 0
            if self.pulse1.length_counter > 0:
                value |= 0x01
            if self.pulse2.length_counter > 0:
                value |= 0x02
            if self.triangle.length_counter > 0:
                value |= 0x04
            if self.noise.length_counter > 0:
                value |= 0x08
            if self.dmc.bytes_remaining > 0:
                value |= 0x10
            if self.frame_irq:
                value |= 0x40
            if self.dmc.irq:
                value |= 0x80
            self.frame_irq = False
            return value
        return 0
    
    def write_register(self, address, value):
        """Write to APU register"""
        # Pulse 1
        if address == 0x4000:
            self.pulse1.write_control(value)
        elif address == 0x4001:
            self.pulse1.write_sweep(value)
        elif address == 0x4002:
            self.pulse1.write_timer_low(value)
        elif address == 0x4003:
            self.pulse1.write_timer_high(value)
        
        # Pulse 2
        elif address == 0x4004:
            self.pulse2.write_control(value)
        elif address == 0x4005:
            self.pulse2.write_sweep(value)
        elif address == 0x4006:
            self.pulse2.write_timer_low(value)
        elif address == 0x4007:
            self.pulse2.write_timer_high(value)
        
        # Triangle
        elif address == 0x4008:
            self.triangle.write_control(value)
        elif address == 0x400A:
            self.triangle.write_timer_low(value)
        elif address == 0x400B:
            self.triangle.write_timer_high(value)
        
        # Noise
        elif address == 0x400C:
            self.noise.write_control(value)
        elif address == 0x400E:
            self.noise.write_period(value)
        elif address == 0x400F:
            self.noise.write_length(value)
        
        # DMC
        elif address == 0x4010:
            self.dmc.write_control(value)
        elif address == 0x4011:
            self.dmc.write_direct_load(value)
        elif address == 0x4012:
            self.dmc.write_sample_address(value)
        elif address == 0x4013:
            self.dmc.write_sample_length(value)
        
        # Control
        elif address == 0x4015:
            self.pulse1.enabled = (value & 0x01) != 0
            self.pulse2.enabled = (value & 0x02) != 0
            self.triangle.enabled = (value & 0x04) != 0
            self.noise.enabled = (value & 0x08) != 0
            self.dmc.enabled = (value & 0x10) != 0
            
            if not self.pulse1.enabled:
                self.pulse1.length_counter = 0
            if not self.pulse2.enabled:
                self.pulse2.length_counter = 0
            if not self.triangle.enabled:
                self.triangle.length_counter = 0
            if not self.noise.enabled:
                self.noise.length_counter = 0
            if not self.dmc.enabled:
                self.dmc.bytes_remaining = 0
        
        # Frame counter
        elif address == 0x4017:
            self.frame_mode = (value >> 7) & 1
            self.frame_irq = False
    
    def step(self):
        """Step APU by one CPU cycle"""
        self.clock(1)

    def clock(self, cpu_cycles):
        """Step APU by multiple CPU cycles at once (performance optimization)."""
        old_cycles = self.cycles
        self.cycles += cpu_cycles

        # Check if any frame counter triggers crossed (every 7457 cycles)
        old_frame = old_cycles // 7457
        new_frame = self.cycles // 7457
        for _ in range(new_frame - old_frame):
            self.clock_frame_counter()

        # Inline triangle timer clocking (runs every CPU cycle)
        tri = self.triangle
        remaining = cpu_cycles
        while remaining > 0:
            if tri.timer > 0:
                ticks = min(remaining, tri.timer)
                tri.timer -= ticks
                remaining -= ticks
            else:
                tri.timer = tri.timer_period
                if tri.length_counter > 0 and tri.linear_counter > 0:
                    tri.sequence_pos = (tri.sequence_pos + 1) & 31
                remaining -= 1

        # Inline pulse and noise timer clocking (runs every other CPU cycle)
        half_cycles = cpu_cycles >> 1
        if half_cycles > 0:
            for ch in (self.pulse1, self.pulse2):
                rem = half_cycles
                while rem > 0:
                    if ch.timer > 0:
                        ticks = min(rem, ch.timer)
                        ch.timer -= ticks
                        rem -= ticks
                    else:
                        ch.timer = ch.timer_period
                        ch.sequence_pos = (ch.sequence_pos + 1) & 7
                        rem -= 1

            n = self.noise
            rem = half_cycles
            while rem > 0:
                if n.timer > 0:
                    ticks = min(rem, n.timer)
                    n.timer -= ticks
                    rem -= ticks
                else:
                    n.timer = n.timer_period
                    feedback = (n.shift_register & 1) ^ ((n.shift_register >> (6 if n.mode else 1)) & 1)
                    n.shift_register = (n.shift_register >> 1) | (feedback << 14)
                    rem -= 1
    
    def clock_frame_counter(self):
        """Clock frame counter"""
        self.frame_counter += 1
        
        if self.frame_mode == 0:  # 4-step
            if self.frame_counter == 4:
                self.frame_counter = 0
                self.frame_irq = True
        else:  # 5-step
            if self.frame_counter == 5:
                self.frame_counter = 0
        
        # Clock envelopes and linear counter
        self.pulse1.clock_envelope()
        self.pulse2.clock_envelope()
        self.triangle.clock_linear_counter()
        self.noise.clock_envelope()
        
        # Clock length counters and sweep on half frames
        if self.frame_counter % 2 == 0:
            self.pulse1.clock_length_counter()
            self.pulse1.clock_sweep()
            self.pulse2.clock_length_counter()
            self.pulse2.clock_sweep()
            self.triangle.clock_length_counter()
            self.noise.clock_length_counter()
    
    def sample(self):
        """Generate audio sample"""
        pulse1_out = self.pulse1.output()
        pulse2_out = self.pulse2.output()
        triangle_out = self.triangle.output()
        noise_out = self.noise.output()
        dmc_out = self.dmc.output()
        
        # Mix channels
        pulse_out = 0.00752 * (pulse1_out + pulse2_out)
        tnd_out = 0.00851 * triangle_out + 0.00494 * noise_out + 0.00335 * dmc_out
        
        return pulse_out + tnd_out


class PulseChannel:
    def __init__(self):
        self.enabled = False
        self.duty_cycle = 0
        self.length_counter = 0
        self.length_halt = False
        self.constant_volume = False
        self.volume = 0
        self.timer = 0
        self.timer_period = 0
        self.sequence_pos = 0
        self.envelope_start = False
        self.envelope_divider = 0
        self.envelope_volume = 0
        self.sweep_enabled = False
        self.sweep_period = 0
        self.sweep_negate = False
        self.sweep_shift = 0
        self.sweep_reload = False
        self.sweep_divider = 0
        
        self.duty_sequences = [
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 1, 1, 0, 0, 0, 0, 0],
            [0, 1, 1, 1, 1, 0, 0, 0],
            [1, 0, 0, 1, 1, 1, 1, 1]
        ]
    
    def reset(self):
        self.__init__()
    
    def write_control(self, value):
        self.duty_cycle = (value >> 6) & 3
        self.length_halt = (value & 0x20) != 0
        self.constant_volume = (value & 0x10) != 0
        self.volume = value & 0x0F
    
    def write_sweep(self, value):
        self.sweep_enabled = (value & 0x80) != 0
        self.sweep_period = ((value >> 4) & 7) + 1
        self.sweep_negate = (value & 0x08) != 0
        self.sweep_shift = value & 7
        self.sweep_reload = True
    
    def write_timer_low(self, value):
        self.timer_period = (self.timer_period & 0x0700) | value
    
    def write_timer_high(self, value):
        self.timer_period = (self.timer_period & 0x00FF) | ((value & 7) << 8)
        self.length_counter = [10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
                               12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30][value >> 3]
        self.envelope_start = True
        self.sequence_pos = 0
    
    def clock_timer(self):
        if self.timer == 0:
            self.timer = self.timer_period
            self.sequence_pos = (self.sequence_pos + 1) % 8
        else:
            self.timer -= 1
    
    def clock_envelope(self):
        if self.envelope_start:
            self.envelope_volume = 15
            self.envelope_divider = self.volume
            self.envelope_start = False
        elif self.envelope_divider > 0:
            self.envelope_divider -= 1
        else:
            self.envelope_divider = self.volume
            if self.envelope_volume > 0:
                self.envelope_volume -= 1
            elif self.length_halt:
                self.envelope_volume = 15
    
    def clock_length_counter(self):
        if self.length_counter > 0 and not self.length_halt:
            self.length_counter -= 1
    
    def clock_sweep(self):
        if self.sweep_divider == 0 and self.sweep_enabled:
            change_amount = self.timer_period >> self.sweep_shift
            if self.sweep_negate:
                self.timer_period -= change_amount
            else:
                self.timer_period += change_amount
        
        if self.sweep_divider == 0 or self.sweep_reload:
            self.sweep_divider = self.sweep_period
            self.sweep_reload = False
        else:
            self.sweep_divider -= 1
    
    def output(self):
        if not self.enabled or self.length_counter == 0:
            return 0
        if self.timer_period < 8 or self.timer_period > 0x7FF:
            return 0
        if self.duty_sequences[self.duty_cycle][self.sequence_pos] == 0:
            return 0
        return self.volume if self.constant_volume else self.envelope_volume


class TriangleChannel:
    def __init__(self):
        self.enabled = False
        self.length_counter = 0
        self.length_halt = False
        self.linear_counter = 0
        self.linear_reload = 0
        self.linear_reload_flag = False
        self.timer = 0
        self.timer_period = 0
        self.sequence_pos = 0
        
        self.sequence = [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0,
                         0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    
    def reset(self):
        self.__init__()
    
    def write_control(self, value):
        self.length_halt = (value & 0x80) != 0
        self.linear_reload = value & 0x7F
    
    def write_timer_low(self, value):
        self.timer_period = (self.timer_period & 0x0700) | value
    
    def write_timer_high(self, value):
        self.timer_period = (self.timer_period & 0x00FF) | ((value & 7) << 8)
        self.length_counter = [10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
                               12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30][value >> 3]
        self.linear_reload_flag = True
    
    def clock_timer(self):
        if self.timer == 0:
            self.timer = self.timer_period
            if self.length_counter > 0 and self.linear_counter > 0:
                self.sequence_pos = (self.sequence_pos + 1) % 32
        else:
            self.timer -= 1
    
    def clock_linear_counter(self):
        if self.linear_reload_flag:
            self.linear_counter = self.linear_reload
        elif self.linear_counter > 0:
            self.linear_counter -= 1
        
        if not self.length_halt:
            self.linear_reload_flag = False
    
    def clock_length_counter(self):
        if self.length_counter > 0 and not self.length_halt:
            self.length_counter -= 1
    
    def output(self):
        if not self.enabled or self.length_counter == 0 or self.linear_counter == 0:
            return 0
        return self.sequence[self.sequence_pos]


class NoiseChannel:
    def __init__(self):
        self.enabled = False
        self.length_counter = 0
        self.length_halt = False
        self.constant_volume = False
        self.volume = 0
        self.timer = 0
        self.timer_period = 0
        self.mode = False
        self.shift_register = 1
        self.envelope_start = False
        self.envelope_divider = 0
        self.envelope_volume = 0
        
        self.period_table = [4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068]
    
    def reset(self):
        self.__init__()
    
    def write_control(self, value):
        self.length_halt = (value & 0x20) != 0
        self.constant_volume = (value & 0x10) != 0
        self.volume = value & 0x0F
    
    def write_period(self, value):
        self.mode = (value & 0x80) != 0
        self.timer_period = self.period_table[value & 0x0F]
    
    def write_length(self, value):
        self.length_counter = [10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
                               12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30][value >> 3]
        self.envelope_start = True
    
    def clock_timer(self):
        if self.timer == 0:
            self.timer = self.timer_period
            feedback = (self.shift_register & 1) ^ ((self.shift_register >> (6 if self.mode else 1)) & 1)
            self.shift_register >>= 1
            self.shift_register |= feedback << 14
        else:
            self.timer -= 1
    
    def clock_envelope(self):
        if self.envelope_start:
            self.envelope_volume = 15
            self.envelope_divider = self.volume
            self.envelope_start = False
        elif self.envelope_divider > 0:
            self.envelope_divider -= 1
        else:
            self.envelope_divider = self.volume
            if self.envelope_volume > 0:
                self.envelope_volume -= 1
            elif self.length_halt:
                self.envelope_volume = 15
    
    def clock_length_counter(self):
        if self.length_counter > 0 and not self.length_halt:
            self.length_counter -= 1
    
    def output(self):
        if not self.enabled or self.length_counter == 0:
            return 0
        if self.shift_register & 1:
            return 0
        return self.volume if self.constant_volume else self.envelope_volume


class DMCChannel:
    def __init__(self):
        self.enabled = False
        self.irq = False
        self.loop = False
        self.rate = 0
        self.output_level = 0
        self.sample_address = 0
        self.sample_length = 0
        self.current_address = 0
        self.bytes_remaining = 0
        
        self.rate_table = [428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142, 128, 106, 84, 72, 54]
    
    def reset(self):
        self.__init__()
    
    def write_control(self, value):
        self.irq = (value & 0x80) != 0
        self.loop = (value & 0x40) != 0
        self.rate = self.rate_table[value & 0x0F]
    
    def write_direct_load(self, value):
        self.output_level = value & 0x7F
    
    def write_sample_address(self, value):
        self.sample_address = 0xC000 + value * 64
    
    def write_sample_length(self, value):
        self.sample_length = value * 16 + 1
    
    def output(self):
        return self.output_level
