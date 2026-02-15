"""
NES Controller Input
"""

class Controller:
    def __init__(self):
        self.buttons = {
            'A': False,
            'B': False,
            'SELECT': False,
            'START': False,
            'UP': False,
            'DOWN': False,
            'LEFT': False,
            'RIGHT': False
        }
        self.index = 0
        self.strobe = 0
    
    def write(self, value):
        """Write to controller (strobe)"""
        self.strobe = value & 1
        if self.strobe:
            self.index = 0
    
    def read(self):
        """Read controller state"""
        if self.index > 7:
            return 1
        
        # Button order: A, B, Select, Start, Up, Down, Left, Right
        button_order = ['A', 'B', 'SELECT', 'START', 'UP', 'DOWN', 'LEFT', 'RIGHT']
        value = 1 if self.buttons[button_order[self.index]] else 0
        
        if not self.strobe:
            self.index += 1
        
        return value | 0x40  # Open bus bits
    
    def set_button(self, button, pressed):
        """Set button state"""
        if button in self.buttons:
            self.buttons[button] = pressed
