"""Scrollable Windows-style controller test panel, using actual enumerated inputs."""
import math
import tkinter as tk
from tkinter import ttk


class ControllerDashboard(ttk.Frame):
    def __init__(self, parent, select_input, label, compact=False):
        super().__init__(parent)
        self.select_input, self.label = select_input, label
        self.compact = compact
        self.objects, self.values = [], {}
        self.signature = None
        self.selected_offset = None
        self.hit_regions = []
        self.button_regions = []
        button_frame = ttk.Frame(self)
        button_frame.pack(side='bottom', fill='x', pady=(6, 0))
        self.button_canvas = tk.Canvas(button_frame, bg='white', highlightthickness=1, highlightbackground='#d5dce6', height=125)
        button_scroll = ttk.Scrollbar(button_frame, orient='vertical', command=self.button_canvas.yview)
        self.button_canvas.configure(yscrollcommand=button_scroll.set)
        button_scroll.pack(side='right', fill='y')
        self.button_canvas.pack(side='left', fill='x', expand=True)
        self.button_canvas.bind('<Configure>', lambda _: self.draw())
        self.button_canvas.bind('<Button-1>', self.clicked_button)
        self.button_canvas.bind('<MouseWheel>', lambda e: self.button_canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.canvas = tk.Canvas(self, bg='white', highlightthickness=1,
                                highlightbackground='#d5dce6', height=320)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.draw())
        self.canvas.bind('<Button-1>', self.clicked)
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))

    def update_inputs(self, objects, values):
        self.objects, self.values = list(objects), dict(values)
        signature = (self.selected_offset, tuple((id(obj), self.label(obj)) for obj in objects),
                     tuple((offset, round(value, 3)) for offset, value in sorted(values.items())))
        if signature == self.signature:
            return
        self.signature = signature
        self.draw()

    def clicked(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for left, top, right, bottom, obj in self.hit_regions:
            if left <= x <= right and top <= y <= bottom:
                self.select_input(obj)
                break

    def clicked_button(self, event):
        x, y = self.button_canvas.canvasx(event.x), self.button_canvas.canvasy(event.y)
        for left, top, right, bottom, obj in self.button_regions:
            if left <= x <= right and top <= y <= bottom:
                self.select_input(obj)
                break

    def draw(self):
        c, width = self.canvas, max(290, self.canvas.winfo_width())
        c.delete('all')
        self.button_canvas.delete('all')
        self.hit_regions = []
        self.button_regions = []
        if not self.objects:
            c.create_text(16, 25, anchor='w', text='Connect a controller to see live inputs.', fill='#59677b')
            return
        y = 20
        text = lambda x, y, value, **kw: c.create_text(x, y, text=value, fill='#243247', font=('Segoe UI', 9), **kw)
        axes = [o for o in self.objects if o.kind == 'axis']
        xy = {o.axis: o for o in axes if o.axis in ('X', 'Y')}
        if len(xy) == 2 and not self.compact:
            text(16, y, 'X / Y position', anchor='w')
            c.create_rectangle(16, y + 15, 108, y + 107, outline='#8899ad')
            c.create_line(62, y + 15, 62, y + 107, fill='#e0e6ee')
            c.create_line(16, y + 61, 108, y + 61, fill='#e0e6ee')
            x = 62 + 44 * self.values.get(xy['X'].offset, 0)
            yy = y + 61 + 44 * self.values.get(xy['Y'].offset, 0)
            c.create_line(x - 5, yy, x + 5, yy, fill='#195cf2', width=2)
            c.create_line(x, yy - 5, x, yy + 5, fill='#195cf2', width=2)
            text(125, y + 40, f"X: {self.values.get(xy['X'].offset, 0):+.3f}", anchor='w')
            text(125, y + 66, f"Y: {self.values.get(xy['Y'].offset, 0):+.3f}", anchor='w')
            y += 132
        for obj in axes:
            value = max(-1, min(1, self.values.get(obj.offset, 0)))
            if obj.offset == self.selected_offset:
                c.create_rectangle(3, y - 12, width - 3, y + 46, outline='#195cf2')
            text(16, y, self.label(obj), anchor='w', width=width - 145)
            mouse = getattr(obj, 'family', '') == 'mouse'
            text(width - 16, y, f'{value * 200:+.0f}px' if mouse else f'{value:+.3f} / {100 * value:+.1f}%', anchor='e')
            left, right, center = 18, width - 18, width / 2
            position = left + (right - left) * (value + 1) / 2
            c.create_rectangle(left, y + 12, right, y + 24, fill='#e7ebf1', outline='')
            c.create_rectangle(min(center, position), y + 12, max(center, position), y + 24, fill='#b62749', outline='')
            c.create_line(position, y + 9, position, y + 27, fill='#861b36', width=2)
            for fraction, label in ((0, '−200px' if mouse else '−1 / −100%'), (.5, '0'), (1, '+200px' if mouse else '+1 / +100%')):
                xx = left + (right - left) * fraction
                c.create_line(xx, y + 24, xx, y + 29, fill='#8899ad')
                text(xx, y + 37, label, anchor='w' if fraction == 0 else 'e' if fraction == 1 else 'center')
            self.hit_regions.append((0, y - 9, width, y + 45, obj))
            y += 62
        buttons = [o for o in self.objects if o.kind == 'button']
        if buttons:
            bc, bw = self.button_canvas, max(290, self.button_canvas.winfo_width())
            bc.create_text(16, 14, text=f'Buttons · {sum(bool(self.values.get(o.offset)) for o in buttons)} pressed', anchor='w', fill='#243247', font=('Segoe UI', 9))
            keyboard = any(getattr(o, 'family', '') == 'keyboard' for o in buttons)
            cell_width, cell_height = (85, 32) if keyboard else (38, 38)
            columns = max(1, (bw - 24) // cell_width)
            for index, obj in enumerate(buttons):
                xx, yy = (54 if keyboard else 30) + index % columns * cell_width, 43 + index // columns * cell_height
                pressed = bool(self.values.get(obj.offset))
                draw = bc.create_rectangle if keyboard else bc.create_oval
                radius = 39 if keyboard else 13
                draw(xx - radius, yy - 13, xx + radius, yy + 13,
                              fill='#ed244b' if pressed else '#771c2c', outline='#195cf2' if obj.offset == self.selected_offset else '#243247',
                              width=3 if obj.offset == self.selected_offset else 2 if pressed else 1)
                bc.create_text(xx, yy, text=obj.name[:11] if keyboard else str(obj.index + 1), fill='white', font=('Segoe UI', 8 if keyboard else 9, 'bold'))
                self.button_regions.append((xx - radius, yy - 15, xx + radius, yy + 15, obj))
            height = 30 + math.ceil(len(buttons) / columns) * cell_height
            available = max(120, self.winfo_height())
            visible = min(150, height, max(58, available // 2)) if self.compact else min(150, height)
            bc.configure(height=visible, scrollregion=(0, 0, bw, height))
        else:
            self.button_canvas.configure(height=26)
            self.button_canvas.create_text(16, 14, text='No buttons reported', anchor='w', fill='#59677b')
        for obj in (o for o in self.objects if o.kind == 'pov'):
            value = self.values.get(obj.offset, -1)
            text(16, y + 20, self.label(obj), anchor='w', width=width - 135)
            cx, cy = width - 70, y + 23
            c.create_oval(cx - 20, cy - 20, cx + 20, cy + 20, outline='#8899ad')
            if value >= 0:
                angle = math.radians(value / 100)
                c.create_line(cx, cy, cx + 18 * math.sin(angle), cy - 18 * math.cos(angle), fill='#ed244b', width=3, arrow='last')
            text(width - 16, y + 52, 'Centered' if value < 0 else f'{value / 100:.0f}°', anchor='e')
            self.hit_regions.append((0, y, width, y + 65, obj))
            y += 70
        c.configure(scrollregion=(0, 0, width, y + 5))
