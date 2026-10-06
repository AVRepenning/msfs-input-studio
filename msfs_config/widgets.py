import tkinter as tk
from tkinter import ttk


class ScrollPage(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background='#edf1f5', highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, padding=12)
        self.item = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.item, width=e.width))
        self.content.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.bind_id = self.winfo_toplevel().bind('<MouseWheel>', self.wheel, add='+')
        self.bind('<Destroy>', self.destroyed)

    def wheel(self, event):
        if getattr(self.winfo_toplevel(), 'capturing_mouse', False):
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self:
                self.canvas.yview_scroll(-int(event.delta / 120), 'units')
                return
            widget = getattr(widget, 'master', None)

    def destroyed(self, event):
        if event.widget is self:
            self.winfo_toplevel().unbind('<MouseWheel>', self.bind_id)
