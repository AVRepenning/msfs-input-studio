from copy import deepcopy
import ctypes
import json
import math
import os
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import __version__
from .catalogue import Catalogue, display_name
from .devices import DirectInput, changed_inputs
from .locations import simulator_locations
from .labels import ControllerLabels
from .profiles import Profile, AXES, AXIS_DEFAULTS, FLAGS

CATEGORIES = {'General controls': 'GENERAL', 'Airplane controls': 'AIRPLANE', 'Helicopter controls': 'HELICOPTER'}
AXIS_LABELS = {'AxisSensitivy': 'Sensitivity +', 'AxisSensitivyMinus': 'Sensitivity −',
               'AxisDeadZone': 'Inner deadzone', 'AxisOutDeadZone': 'Outer deadzone',
               'AxisNeutral': 'Neutral', 'AxisResponseRate': 'Response rate'}


class App:
    def __init__(self, root, user_library=True):
        self.root = root
        self.root.title('MSFS Input Studio')
        self.root.geometry('1340x890')
        self.root.minsize(1120, 740)
        self.catalogue = Catalogue(storage=user_library)
        self.labels = ControllerLabels(storage=user_library)
        self.profile = None
        self.path = None
        self.saved_text = None
        self.history, self.future = [], []
        self.backend = None
        self.controller = None
        self.devices = []
        self.current_values = {}
        self.capture = None
        self.recording = None
        self.input_choice_names = {}
        self.selected = None
        self.sort_column, self.sort_reverse = 'name', False
        self.refresh_job = None
        self.loading = False
        self.current_profile_category = 'GENERAL'
        self.status = tk.StringVar(value='Choose a controller or open an exported XML profile to begin.')
        self.device_var = tk.StringVar()
        self.name_var = tk.StringVar(value='My flight controls')
        self.type_var = tk.StringVar(value='General controls')
        self.search_var = tk.StringVar()
        self.context_var = tk.StringVar(value='All contexts')
        self.bound_only = tk.BooleanVar()
        self.conflicts_only = tk.BooleanVar()
        self.input_filter = None
        self.show_all = tk.BooleanVar()
        self.split_axes = tk.BooleanVar()
        self.slot_vars = {slot: tk.StringVar() for slot in ('Primary', 'Secondary')}
        self.slot_keys = {slot: [] for slot in self.slot_vars}
        self.input_vars = {slot: tk.StringVar() for slot in self.slot_vars}
        self.flag_vars = {bit: tk.BooleanVar() for bit in FLAGS}
        self.flag_value = tk.StringVar(value='2')
        self.event_value = tk.StringVar(value='0')
        self.delay_value = tk.StringVar(value='0')
        self.axis_var = tk.StringVar(value='X')
        self.axis_scope = tk.StringVar(value='Global axis')
        self.axis_values = {name: tk.StringVar(value=value) for name, value in AXIS_DEFAULTS.items()}
        self.monitor_status = tk.StringVar(value='No controller connected for live input.')
        self.input_label_var = tk.StringVar()
        self.record_slot = tk.StringVar(value='Primary')
        self._style()
        self._build()
        for var in (self.search_var, self.context_var, self.bound_only, self.show_all, self.conflicts_only):
            var.trace_add('write', self.schedule_list)
        self.name_var.trace_add('write', self.rename_profile)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.bind('<Control-o>', lambda _: self.open_profile())
        self.root.bind('<Control-s>', lambda _: self.save_profile())
        self.root.bind('<Control-z>', lambda _: self.undo())
        self.root.bind('<Control-y>', lambda _: self.redo())
        self.root.bind('<Escape>', lambda _: self.cancel_capture())
        self.root.after(80, self.refresh_devices)
        self.root.after(150, self.poll)
        self.refresh_list()

    def _style(self):
        self.root.configure(bg='#edf1f5')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#edf1f5', foreground='#243247')
        style.configure('TButton', padding=(10, 7))
        style.configure('Accent.TButton', background='#195cf2', foreground='white')
        style.map('Accent.TButton', background=[('active', '#1549c0')])
        style.configure('Title.TLabel', font=('Segoe UI Semibold', 24))
        style.configure('Heading.TLabel', font=('Segoe UI Semibold', 12))
        style.configure('Muted.TLabel', foreground='#59677b')
        style.configure('Treeview', background='white', fieldbackground='white', rowheight=29, borderwidth=0)
        style.configure('Treeview.Heading', font=('Segoe UI Semibold', 10), padding=7)
        style.map('Treeview', background=[('selected', '#e3edff')], foreground=[('selected', '#103b8b')])
        style.configure('TLabelframe', padding=12)
        style.configure('TNotebook.Tab', padding=(13, 8))

    def _build(self):
        shell = ttk.Frame(self.root, padding=20)
        shell.pack(fill='both', expand=True)
        header = ttk.Frame(shell)
        header.pack(fill='x')
        ttk.Label(header, text='MSFS Input Studio', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='Configure here. Fly later.', style='Muted.TLabel').pack(side='left', padx=20, pady=12)
        ttk.Button(header, text='Import guide', command=self.import_guide).pack(side='right')
        ttk.Button(header, text='Help', command=self.help).pack(side='right', padx=6)

        device_row = ttk.Frame(shell, padding=(0, 15, 0, 8))
        device_row.pack(fill='x')
        ttk.Label(device_row, text='Controller', style='Heading.TLabel').pack(side='left', padx=(0, 12))
        self.device_combo = ttk.Combobox(device_row, textvariable=self.device_var, state='readonly', width=51)
        self.device_combo.pack(side='left')
        self.device_combo.bind('<<ComboboxSelected>>', self.select_device)
        ttk.Button(device_row, text='Refresh', command=self.refresh_devices).pack(side='left', padx=6)
        ttk.Button(device_row, text='Use for this profile', command=self.retarget).pack(side='left')
        self.device_summary = ttk.Label(device_row, text='Reading Windows controllers…', style='Muted.TLabel')
        self.device_summary.pack(side='left', padx=12)

        toolbar = ttk.Frame(shell, padding=(0, 3, 0, 16))
        toolbar.pack(fill='x')
        ttk.Label(toolbar, text='Profile').pack(side='left', padx=(0, 8))
        ttk.Entry(toolbar, textvariable=self.name_var, width=25).pack(side='left')
        self.category_combo = ttk.Combobox(toolbar, textvariable=self.type_var, values=list(CATEGORIES), state='readonly', width=20)
        self.category_combo.pack(side='left', padx=8)
        self.category_combo.bind('<<ComboboxSelected>>', self.category_changed)
        for label, command in [('New', self.new_profile), ('Open XML', self.open_profile),
                               ('Duplicate', self.duplicate), ('Undo', self.undo), ('Redo', self.redo)]:
            ttk.Button(toolbar, text=label, command=command).pack(side='left', padx=2)
        ttk.Button(toolbar, text='Export XML', style='Accent.TButton', command=self.save_profile).pack(side='right')

        body = ttk.Panedwindow(shell, orient='horizontal')
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body)
        right = ttk.Frame(body, padding=(15, 0, 0, 0))
        body.add(left, weight=3)
        body.add(right, weight=2)
        ttk.Label(left, text='Find a control', style='Heading.TLabel').pack(anchor='w')
        search = ttk.Entry(left, textvariable=self.search_var)
        search.pack(fill='x', pady=(8, 6))
        search.insert(0, '')
        filters = ttk.Frame(left)
        filters.pack(fill='x', pady=(0, 7))
        self.context_combo = ttk.Combobox(filters, textvariable=self.context_var, state='readonly', width=25,
                                        values=['All contexts'] + sorted({a[0] for a in self.catalogue.actions}))
        self.context_combo.pack(side='left')
        ttk.Checkbutton(filters, text='Bound only', variable=self.bound_only).pack(side='left', padx=8)
        ttk.Checkbutton(filters, text='All profile types', variable=self.show_all).pack(side='left')
        ttk.Checkbutton(filters, text='Conflicts', variable=self.conflicts_only).pack(side='left', padx=5)
        recording_row = ttk.Frame(left)
        recording_row.pack(fill='x', pady=(0, 7))
        ttk.Button(recording_row, text='Record selected', style='Accent.TButton', command=self.record_selected).pack(side='left')
        ttk.Combobox(recording_row, textvariable=self.record_slot, values=['Primary', 'Secondary'], state='readonly', width=11).pack(side='left', padx=5)
        ttk.Button(recording_row, text='Skip', command=self.skip_recording).pack(side='left')
        ttk.Button(recording_row, text='Stop', command=self.stop_recording).pack(side='left', padx=5)
        ttk.Button(recording_row, text='Find input', command=self.find_input).pack(side='left')
        ttk.Button(recording_row, text='Clear input filter', command=self.clear_input_filter).pack(side='left', padx=5)
        table = ttk.Frame(left)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('action', 'context', 'binding'), show='headings', selectmode='extended')
        for column, title, width in [('action', 'Action', 290), ('context', 'Context', 145), ('binding', 'Binding', 175)]:
            self.tree.heading(column, text=title, command=lambda c=column: self.sort(c))
            self.tree.column(column, width=width, minwidth=70)
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.tag_configure('unavailable', foreground='#919aaa')
        self.tree.tag_configure('bound', foreground='#185ba8')
        self.tree.bind('<<TreeviewSelect>>', self.select_action)
        self.count_label = ttk.Label(left, text='', style='Muted.TLabel')
        self.count_label.pack(anchor='w', pady=7)

        self.action_title = ttk.Label(right, text='Select a control', style='Heading.TLabel', wraplength=445)
        self.action_title.pack(anchor='w')
        self.action_id = ttk.Label(right, text='Search by name, event ID or context.', style='Muted.TLabel', wraplength=440)
        self.action_id.pack(anchor='w', pady=(5, 12))
        tabs = ttk.Notebook(right)
        tabs.pack(fill='both', expand=True)
        binding_page, behavior_page, axis_page, monitor_page = (ttk.Frame(tabs, padding=12) for _ in range(4))
        tabs.add(binding_page, text='Bindings')
        tabs.add(behavior_page, text='Behavior')
        tabs.add(axis_page, text='Axis tuning')
        tabs.add(monitor_page, text='Live inputs')
        self.input_combos = {}
        for slot in self.slot_vars:
            card = ttk.LabelFrame(binding_page, text=slot)
            card.pack(fill='x', pady=(0, 10))
            ttk.Label(card, textvariable=self.slot_vars[slot], wraplength=410).pack(fill='x', pady=(0, 8))
            combo = ttk.Combobox(card, textvariable=self.input_vars[slot], state='readonly')
            combo.pack(fill='x')
            self.input_combos[slot] = combo
            buttons = ttk.Frame(card)
            buttons.pack(fill='x', pady=(7, 0))
            for label, cmd in [('Use', lambda s=slot: self.manual_binding(s)),
                               ('Add to chord', lambda s=slot: self.manual_binding(s, True)),
                               ('Get Input', lambda s=slot: self.start_capture(s)),
                               ('Clear', lambda s=slot: self.clear_binding(s))]:
                ttk.Button(buttons, text=label, command=cmd).pack(side='left', padx=(0, 3))
        capture_row = ttk.Frame(binding_page)
        capture_row.pack(fill='x')
        ttk.Checkbutton(capture_row, text='Capture split axis (+ / −)', variable=self.split_axes).pack(side='left')
        ttk.Button(capture_row, text='Cancel capture', command=self.cancel_capture).pack(side='right')
        ttk.Label(behavior_page, text='Digital repeats while held. Once on press sends a single event. On release triggers when you release the button.',
                  style='Muted.TLabel', wraplength=415).pack(anchor='w', pady=(0, 12))
        options = ttk.LabelFrame(behavior_page, text='Action behavior', padding=8)
        options.pack(fill='x', pady=(9, 0))
        for index, (bit, label) in enumerate(FLAGS.items()):
            ttk.Checkbutton(options, text=label, variable=self.flag_vars[bit], command=self.flags_changed).grid(
                row=index // 3, column=index % 3, sticky='w', padx=3, pady=1)
        fields = ttk.Frame(options)
        fields.grid(row=6, column=0, columnspan=3, sticky='ew', pady=7)
        for label, var in [('Flags', self.flag_value), ('Value', self.event_value), ('Delay (s)', self.delay_value)]:
            ttk.Label(fields, text=label).pack(side='left', padx=(0, 4))
            ttk.Entry(fields, textvariable=var, width=8).pack(side='left', padx=(0, 8))
        ttk.Button(options, text='Apply behavior', command=self.apply_behavior).grid(row=7, column=0, columnspan=3, sticky='ew')

        ttk.Label(axis_page, text='Axis settings are saved to the profile.', style='Muted.TLabel', wraplength=420).pack(anchor='w')
        row = ttk.Frame(axis_page)
        row.pack(fill='x', pady=10)
        axis_combo = ttk.Combobox(row, textvariable=self.axis_var, values=AXES, width=11, state='readonly')
        axis_combo.pack(side='left')
        axis_combo.bind('<<ComboboxSelected>>', lambda _: self.load_axis())
        scope = ttk.Combobox(row, textvariable=self.axis_scope, values=['Global axis', 'Primary override', 'Secondary override'], state='readonly', width=21)
        scope.pack(side='left', padx=8)
        scope.bind('<<ComboboxSelected>>', lambda _: self.load_axis())
        for attr, label in AXIS_LABELS.items():
            row = ttk.Frame(axis_page)
            row.pack(fill='x', pady=6)
            ttk.Label(row, text=label, width=20).pack(side='left')
            low, high = ((-1, 2000) if attr == 'AxisResponseRate' else (0, 100) if 'DeadZone' in attr else (-100, 100))
            spin = ttk.Spinbox(row, from_=low, to=high, increment=1, textvariable=self.axis_values[attr], width=9)
            spin.pack(side='left')
        ttk.Label(axis_page, text='Sensitivity / neutral: −100 to 100. Deadzones: 0–100.\nResponse rate: −1 for default, or 100–2000.', style='Muted.TLabel').pack(anchor='w', pady=10)
        ttk.Button(axis_page, text='Apply axis settings', style='Accent.TButton', command=self.apply_axis).pack(fill='x', pady=8)
        ttk.Label(axis_page, text='Live axis position', style='Heading.TLabel').pack(anchor='w', pady=(15, 5))
        self.axis_canvas = tk.Canvas(axis_page, height=90, bg='white', highlightthickness=0)
        self.axis_canvas.pack(fill='x')
        ttk.Label(axis_page, text='This shows raw controller input. MSFS applies the saved sensitivity curve during flight.', style='Muted.TLabel', wraplength=410).pack(anchor='w', pady=8)

        ttk.Label(monitor_page, textvariable=self.monitor_status, wraplength=420, style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        ttk.Label(monitor_page, text='Name any input: select a row, enter a label, then Set name.', style='Muted.TLabel', wraplength=420).pack(anchor='w', pady=(0, 5))
        naming = ttk.Frame(monitor_page)
        naming.pack(fill='x', pady=(0, 10))
        ttk.Entry(naming, textvariable=self.input_label_var, width=24).pack(side='left', fill='x', expand=True)
        ttk.Button(naming, text='Set name', command=self.set_input_label).pack(side='left', padx=4)
        ttk.Button(naming, text='Reset', command=lambda: self.set_input_label(reset=True)).pack(side='left')
        self.monitor = ttk.Treeview(monitor_page, columns=('input', 'value', 'support'), show='headings', height=14)
        for column, title, width in [('input', 'Windows input', 160), ('value', 'Value', 70), ('support', 'XML ID', 95)]:
            self.monitor.heading(column, text=title)
            self.monitor.column(column, width=width, minwidth=50)
        scroll = ttk.Scrollbar(monitor_page, orient='vertical', command=self.monitor.yview)
        self.monitor.configure(yscrollcommand=scroll.set)
        self.monitor.pack(side='left', fill='both', expand=True)
        self.monitor.bind('<<TreeviewSelect>>', self.select_monitor_input)
        scroll.pack(side='right', fill='y')
        ttk.Label(shell, textvariable=self.status, wraplength=1250, style='Muted.TLabel').pack(
            before=body, side='bottom', fill='x', pady=(12, 0))

    def error(self, exc):
        messagebox.showerror('MSFS Input Studio', str(exc), parent=self.root)

    def checkpoint(self):
        if self.profile:
            self.history.append(self.profile.to_text())
            self.history = self.history[-60:]
            self.future.clear()

    def dirty(self):
        return self.profile is not None and self.profile.to_text() != self.saved_text

    def can_discard(self):
        if not self.dirty():
            return True
        result = messagebox.askyesnocancel('Unsaved profile', 'Export your changes before continuing?', parent=self.root)
        if result is None:
            return False
        return self.save_profile() if result else True

    def refresh_devices(self):
        previous = self.device_var.get()
        self.cancel_capture()
        if self.controller:
            self.controller.close()
            self.controller = None
        try:
            if self.backend is None:
                self.backend = DirectInput()
            self.devices = self.backend.enumerate()
            names = [f'{d.name}  [{d.instance_guid[1:9]}]' for d in self.devices]
            self.device_combo.configure(values=names)
            if names:
                self.device_var.set(previous if previous in names else names[0])
                self.select_device()
            else:
                self.device_var.set('No game controllers detected')
                self.device_summary.configure(text='Plug in a controller, then Refresh.')
                self.monitor_status.set('Offline editing is available through Open XML.')
                self.monitor.delete(*self.monitor.get_children())
                self.update_input_choices()
        except Exception as exc:
            self.device_summary.configure(text='Windows input unavailable')
            self.status.set(str(exc))

    def selected_device(self):
        index = self.device_combo.current()
        return self.devices[index] if 0 <= index < len(self.devices) else None

    def select_device(self, _=None):
        self.cancel_capture()
        if self.controller:
            self.controller.close()
            self.controller = None
        device = self.selected_device()
        if not device:
            return
        try:
            self.root.update_idletasks()
            user32 = ctypes.WinDLL('user32.dll')
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetAncestor.restype = ctypes.c_void_p
            hwnd = user32.GetAncestor(self.root.winfo_id(), 2)
            self.controller = self.backend.open(device, hwnd)
            self.current_values = self.controller.read()
            counts = [sum(o.kind == kind for o in device.objects) for kind in ('axis', 'button', 'pov')]
            self.device_summary.configure(text=f'{counts[0]} axes · {counts[1]} buttons · {counts[2]} hats')
            self.monitor_status.set(f'{device.name}\nUSB {device.vendor_id:04X}:{device.product_id:04X} · DirectInput')
            self.monitor.delete(*self.monitor.get_children())
            for obj in device.objects:
                pair = self.catalogue.resolve(obj.msfs_name()) if obj.kind != 'pov' else self.catalogue.resolve(obj.msfs_name('Up'))
                label = self.labels.get(device.instance_guid, obj.msfs_name()) or obj.name
                self.monitor.insert('', 'end', iid=str(obj.offset), values=(label, '—', str(pair[1]) if pair else 'Needs reference'))
            self.update_input_choices()
            if self.profile is None:
                self.new_profile()
            elif self.profile.device.get('GUID', '').lower() != device.instance_guid.lower():
                self.status.set('Live controller differs from the profile. Use for this profile to transfer it explicitly.')
        except Exception as exc:
            self.device_summary.configure(text='Cannot read controller')
            self.status.set(str(exc))

    def update_input_choices(self):
        choices = set()
        device = self.selected_device()
        if device and device.objects:
            from .devices import POV_DIRECTIONS
            for obj in device.objects:
                candidates = ([obj.msfs_name(d) for d in POV_DIRECTIONS] if obj.kind == 'pov' else
                              [obj.msfs_name(d) for d in ('', '+', '-')] if obj.kind == 'axis' else [obj.msfs_name()])
                for name in candidates:
                    pair = self.catalogue.resolve(name)
                    choices.add(pair[0] if pair else name + ' [needs reference]')
        else:
            choices = set(self.catalogue.key_pairs)
        guid = device.instance_guid if device else self.profile.device.get('GUID', '') if self.profile else ''
        self.input_choice_names = {}
        for name in choices:
            label = self.labels.get(guid, name.removesuffix(' [needs reference]'))
            rendered = f'{label} · {name}' if label else name
            self.input_choice_names[rendered] = name
        for combo in self.input_combos.values():
            combo.configure(values=sorted(self.input_choice_names))
        for var in self.input_vars.values():
            var.set('')

    def input_display(self, name, guid=None):
        if guid is None:
            guid = self.profile.device.get('GUID', '') if self.profile else ''
        label = self.labels.get(guid, name)
        return f'{label} ({name.strip()})' if label else name.strip()

    def select_monitor_input(self, _=None):
        selected = self.monitor.selection()
        device = self.selected_device()
        if selected and device:
            obj = next((o for o in device.objects if str(o.offset) == selected[0]), None)
            if obj:
                self.input_label_var.set(self.labels.get(device.instance_guid, obj.msfs_name()) or obj.name)

    def set_input_label(self, reset=False):
        selected = self.monitor.selection()
        device = self.selected_device()
        if not selected or not device:
            self.error('Select an input in Live inputs first.')
            return
        obj = next(o for o in device.objects if str(o.offset) == selected[0])
        try:
            self.labels.set(device.instance_guid, obj.msfs_name(), '' if reset else self.input_label_var.get())
            label = self.labels.get(device.instance_guid, obj.msfs_name()) or obj.name
            self.monitor.set(selected[0], 'input', label)
            self.input_label_var.set(label)
            self.update_input_choices()
            self.refresh_list()
            self.show_action()
            self.status.set(f'Input named {label}. Its original MSFS input name and ID are unchanged.')
        except (OSError, ValueError) as exc:
            self.error(exc)

    def new_profile(self):
        device = self.selected_device()
        if not device:
            self.error('Connect a Windows controller, then Refresh, or open an exported XML profile.')
            return
        if not self.can_discard():
            return
        self.profile = Profile.new(self.name_var.get().strip() or 'My flight controls', device.attributes,
                                   CATEGORIES[self.type_var.get()], [o.axis for o in device.objects if o.kind == 'axis'])
        self.path, self.saved_text = None, None
        self.history, self.future = [], []
        self.current_profile_category = self.profile.category
        self.selected = None
        self.action_title.configure(text='Select a control')
        self.action_id.configure(text='Search by name, event ID or context.')
        for slot in self.slot_vars:
            self.slot_keys[slot] = []
            self.slot_vars[slot].set('Unbound')
        self.refresh_list()
        self.load_axis()
        self.status.set('New profile. Choose a control, then click Get Input or choose a Windows input.')

    def open_profile(self):
        if not self.can_discard():
            return
        path = filedialog.askopenfilename(title='Open MSFS 2024 exported profile', filetypes=[('XML profiles', '*.xml'), ('All files', '*.*')])
        if not path:
            return
        try:
            profile = Profile.load(path)
            self.catalogue.learn(profile)
            self.catalogue.save_library()
            self.profile, self.path = profile, Path(path)
            sidecar = self.path.with_suffix('.studio.json')
            if sidecar.is_file() and sidecar.stat().st_size < 1_000_000:
                try:
                    self.labels.merge(json.loads(sidecar.read_text(encoding='utf-8')).get('controller_labels', {}))
                    self.labels.save()
                except (OSError, ValueError, TypeError) as exc:
                    self.status.set(f'Profile opened; could not load its input labels: {exc}')
            self.saved_text = profile.to_text()
            self.history, self.future = [], []
            self.sync_profile()
            self.update_input_choices()
            self.context_combo.configure(values=['All contexts'] + sorted({a[0] for a in self.catalogue.actions}))
            self.status.set(f'Opened {self.path.name} · {profile.device.get("DeviceName")} · {profile.format} XML')
        except Exception as exc:
            self.error(exc)

    def sync_profile(self):
        self.loading = True
        self.name_var.set(self.profile.name)
        self.type_var.set(next((label for label, value in CATEGORIES.items() if value == self.profile.category), 'Airplane controls'))
        self.current_profile_category = self.profile.category
        self.loading = False
        self.category_combo.configure(state='readonly' if self.profile.category in CATEGORIES.values() else 'disabled')
        self.refresh_list()
        self.show_action()
        self.load_axis()

    def rename_profile(self, *_):
        if not self.loading and self.profile:
            self.profile.name = self.name_var.get()

    def category_changed(self, _=None):
        if self.profile:
            # Different profile types are distinct documents: keep an existing one
            # intact and create a fresh profile explicitly through New.
            chosen = self.type_var.get()
            if CATEGORIES[chosen] != self.profile.category:
                if self.new_profile_for_category(chosen):
                    return
                self.type_var.set(next((k for k, v in CATEGORIES.items() if v == self.profile.category), 'Airplane controls'))
        self.refresh_list()

    def new_profile_for_category(self, chosen):
        if not self.selected_device():
            self.error('Connect a controller to create a new profile type. Open an existing export for offline editing.')
            return False
        self.new_profile()
        return self.profile.category == CATEGORIES[chosen]

    def duplicate(self):
        if not self.profile:
            return
        self.checkpoint()
        self.profile.name = self.profile.name + ' copy'
        self.path = None
        self.sync_profile()
        self.status.set('Duplicated. Export XML to save the copy as a new file.')

    def retarget(self):
        device = self.selected_device()
        if not self.profile or not device:
            return
        self.checkpoint()
        original_guid = self.profile.device.get('GUID', '').lower()
        inherited = self.labels.devices.get(original_guid, {})
        if inherited:
            target = self.labels.devices.setdefault(device.instance_guid.lower(), {})
            for name, label in inherited.items():
                target.setdefault(name, label)
            self.labels.save()
        self.profile.device.attrib.update(device.attributes)
        self.update_input_choices()
        self.refresh_list()
        self.show_action()
        self.status.set(f'Profile now targets {device.name}. Review every binding against its live inputs before importing.')

    def undo(self):
        if self.profile and self.history:
            self.future.append(self.profile.to_text())
            self.profile = Profile.from_text(self.history.pop())
            self.sync_profile()

    def redo(self):
        if self.profile and self.future:
            self.history.append(self.profile.to_text())
            self.profile = Profile.from_text(self.future.pop())
            self.sync_profile()

    def sort(self, column):
        self.sort_reverse = not self.sort_reverse if self.sort_column == column else False
        self.sort_column = column
        self.refresh_list()

    def schedule_list(self, *_):
        if self.refresh_job:
            self.root.after_cancel(self.refresh_job)
        self.refresh_job = self.root.after(150, self.refresh_list)

    def refresh_list(self):
        self.refresh_job = None
        category = self.profile.category if self.profile else CATEGORIES[self.type_var.get()]
        query = self.search_var.get().casefold().split()
        bound = self.profile.actions() if self.profile else {}
        conflict_groups = {}
        for identity, action in bound.items():
            for slot in ('Primary', 'Secondary'):
                keys = self.profile.keys(*identity, slot)
                if keys:
                    # Same complete chord in the SAME context is a potential
                    # conflict. Different contexts may intentionally share it.
                    signature = (identity[0], tuple(sorted(value.strip() for _, value in keys)))
                    conflict_groups.setdefault(signature, set()).add(identity)
        conflicts = set().union(*(group for group in conflict_groups.values() if len(group) > 1)) if conflict_groups else set()
        rows = []
        for identity, entry in self.catalogue.actions.items():
            available = category in entry['categories'] or identity in bound
            if not available and not self.show_all.get():
                continue
            if self.context_var.get() != 'All contexts' and entry['context'] != self.context_var.get():
                continue
            haystack = (display_name(entry['name']) + ' ' + entry['name'] + ' ' + entry['context']).casefold()
            if not all(term in haystack for term in query):
                continue
            action = bound.get(identity)
            names = [k.get('Information', '') for k in action.findall('./Primary/KEY')] if action is not None else []
            secondary = [k.get('Information', '') for k in action.findall('./Secondary/KEY')] if action is not None else []
            binding = ' + '.join(self.input_display(name) for name in names) + (' / ' + ' + '.join(self.input_display(name) for name in secondary) if secondary else '')
            if self.bound_only.get() and not binding:
                continue
            if self.conflicts_only.get() and identity not in conflicts:
                continue
            if self.input_filter is not None and action is not None:
                ids = {str(k.text or '').strip() for k in action.findall('.//KEY')}
                if not self.input_filter.issubset(ids):
                    continue
            elif self.input_filter is not None:
                continue
            rows.append((identity, display_name(entry['name']), entry['context'], binding, available))
        index = {'name': 1, 'action': 1, 'context': 2, 'binding': 3}.get(self.sort_column, 1)
        rows.sort(key=lambda r: (r[index].casefold(), r[0]), reverse=self.sort_reverse)
        self.tree.delete(*self.tree.get_children())
        self.row_ids = {}
        for number, (identity, title, context, binding, available) in enumerate(rows):
            row_id = str(number)
            self.row_ids[row_id] = identity
            self.tree.insert('', 'end', iid=row_id, values=(title, context, binding or '—'),
                             tags=('unavailable',) if not available else ('bound',) if binding else ())
            if self.selected == identity:
                self.tree.selection_set(row_id)
        self.count_label.configure(text=f'{len(rows):,} controls · {sum(bool(r[3]) for r in rows):,} bound · {len(conflicts)} possible conflicts · Ctrl/Shift selects several')

    def select_action(self, _=None):
        selection = self.tree.selection()
        focus = self.tree.focus() if self.tree.focus() in selection else selection[0] if selection else ''
        if focus in self.row_ids:
            identity = self.row_ids[focus]
            if self.recording and identity == self.selected:
                return
            self.cancel_capture()
            self.selected = identity
            self.show_action()

    def show_action(self):
        if not self.selected:
            return
        context, name = self.selected
        self.action_title.configure(text=display_name(name))
        self.action_id.configure(text=f'{name}\n{context}')
        action = self.profile.action(context, name) if self.profile else None
        entry = self.catalogue.actions[self.selected]
        attrs = action.attrib if action is not None else entry['attributes']
        flag = int(attrs.get('Flag', '2'))
        self.flag_value.set(str(flag))
        for bit, var in self.flag_vars.items():
            var.set(bool(flag & bit))
        self.event_value.set(attrs.get('ValueEvent', '0'))
        self.delay_value.set(attrs.get('Delay', '0'))
        for slot in self.slot_vars:
            self.slot_keys[slot] = self.profile.keys(context, name, slot) if self.profile else []
            self.slot_vars[slot].set(' + '.join(self.input_display(k[0]) for k in self.slot_keys[slot]) or 'Unbound')
        self.load_axis()

    def editable(self):
        if not self.profile or not self.selected:
            self.error('Create or open a profile, then select a control.')
            return False
        entry = self.catalogue.actions[self.selected]
        if self.profile.category not in entry['categories'] and self.selected not in self.profile.actions():
            self.error('This control is not available in this profile type. Choose the matching General / Airplane / Helicopter profile.')
            return False
        return True

    def bind(self, slot, pairs, add=False):
        if not self.editable():
            return
        self.checkpoint()
        if add:
            pairs = self.slot_keys[slot] + [p for p in pairs if p not in self.slot_keys[slot]]
        entry = self.catalogue.actions[self.selected]
        self.profile.set_binding(*self.selected, slot, pairs, defaults=entry['attributes'])
        # Let a full-range Windows analog input determine the basic input type;
        # retain modifiers and keep split +/− inputs available for digital actions.
        action = self.profile.action(*self.selected)
        if pairs and any(('axis' in information.casefold() or 'slider' in information.casefold())
                         and not information.rstrip().endswith(('+', '-')) for information, _ in pairs):
            action.set('Flag', str((int(action.get('Flag', '2')) & ~7) | 4))
        self.show_action()
        self.refresh_list()
        self.status.set(f'{slot} binding updated. Export XML when ready.')

    def manual_binding(self, slot, add=False):
        name = self.input_choice_names.get(self.input_vars[slot].get(), self.input_vars[slot].get())
        pair = self.catalogue.resolve(name)
        if not pair:
            self.error('This input has no verified MSFS numeric ID. Open a real MSFS export containing it to learn the ID, then try again.')
            return
        self.bind(slot, [pair], add)

    def clear_binding(self, slot):
        self.bind(slot, [])

    def start_capture(self, slot, guided=False):
        if self.recording and not guided:
            self.stop_recording()
        if not self.editable():
            return
        if not self.controller:
            self.error('Connect a controller and click Refresh before using Get Input.')
            return
        if self.profile.device.get('GUID', '').lower() != self.controller.device.instance_guid.lower():
            self.error('The live controller differs from this profile. Choose Use for this profile before capturing inputs.')
            return
        try:
            baseline = self.controller.read()
            self.capture = {'slot': slot, 'baseline': baseline, 'deadline': time.monotonic() + 12,
                            'names': [], 'settle': None}
            self.status.set(f'Listening for {slot.lower()} input… Move an axis or press a button. Escape cancels.')
            if guided:
                self.status.set(f'Recording {self.recording["index"] + 1}/{len(self.recording["targets"])}: {display_name(self.selected[1])}. Move/press an input; Skip advances, Stop ends.')
        except Exception as exc:
            self.error(exc)

    def cancel_capture(self):
        if self.capture:
            self.capture = None
            self.status.set('Input capture cancelled.')
        self.recording = None

    def record_selected(self):
        selection = self.tree.selection()
        if not selection or not self.profile:
            self.error('Select one or more actions in the list. Use Ctrl or Shift to select several.')
            return
        if not self.controller or self.profile.device.get('GUID', '').lower() != self.controller.device.instance_guid.lower():
            self.error('Select the controller used by this profile before recording.')
            return
        targets = [self.row_ids[row] for row in selection]
        category = self.profile.category
        if any(category not in self.catalogue.actions[target]['categories'] and target not in self.profile.actions() for target in targets):
            self.error('Some selected actions belong to another profile type. Select compatible actions before recording.')
            return
        self.cancel_capture()
        self.recording = {'targets': targets, 'index': 0, 'slot': self.record_slot.get(),
                          'waiting': False, 'stable_since': None, 'last': dict(self.current_values)}
        self.record_next()

    def find_input(self):
        if not self.controller or not self.profile:
            self.error('Open a profile and connect its controller to find bindings by input.')
            return
        if self.profile.device.get('GUID', '').lower() != self.controller.device.instance_guid.lower():
            self.error('Choose the controller used by this profile before searching by input.')
            return
        self.cancel_capture()
        self.capture = {'slot': None, 'baseline': self.controller.read(), 'deadline': time.monotonic() + 12,
                        'names': [], 'settle': None, 'search': True}
        self.status.set('Find input: press a button, move an axis or turn a hat to show its assigned actions.')

    def clear_input_filter(self):
        self.input_filter = None
        self.refresh_list()
        self.status.set('Input filter cleared.')

    def record_next(self):
        if not self.recording:
            return
        session = self.recording
        if session['index'] >= len(session['targets']):
            count = len(session['targets'])
            self.recording = None
            self.capture = None
            self.status.set(f'Recording session finished: {count} actions processed. Review the bindings, then Export XML.')
            return
        self.selected = session['targets'][session['index']]
        session['waiting'] = False
        self.show_action()
        for row, identity in self.row_ids.items():
            if identity == self.selected:
                self.tree.selection_set(row)
                self.tree.focus(row)
                self.tree.see(row)
                break
        self.start_capture(session['slot'], guided=True)

    def skip_recording(self):
        if self.recording:
            self.capture = None
            self.recording['index'] += 1
            self.record_next()

    def stop_recording(self):
        if self.recording:
            self.cancel_capture()
            self.status.set('Recording stopped. Bindings already recorded are kept; Undo can reverse them.')

    def flags_changed(self):
        self.flag_value.set(str(sum(bit for bit, var in self.flag_vars.items() if var.get())))

    def apply_behavior(self):
        if not self.editable():
            return
        try:
            flag = int(self.flag_value.get())
            value, delay = float(self.event_value.get()), float(self.delay_value.get())
            if not 0 <= flag <= 65535 or not math.isfinite(value) or not math.isfinite(delay) or delay < 0:
                raise ValueError('Flags must be 0–65535. Value and delay must be finite; delay must be nonnegative.')
            self.checkpoint()
            action = self.profile.action(*self.selected, create=True, defaults=self.catalogue.actions[self.selected]['attributes'])
            action.attrib.update(Flag=str(flag), ValueEvent=str(value), Delay=str(delay))
            self.show_action()
            self.status.set('Behavior saved. Digital repeats while held; Once on press sends one event. On release triggers on release.')
        except ValueError as exc:
            self.error(exc)

    def load_axis(self):
        values = dict(AXIS_DEFAULTS)
        if self.profile:
            parent = self.profile.device.find('Axes')
            if self.axis_scope.get() != 'Global axis':
                action = self.profile.action(*self.selected) if self.selected else None
                parent = action.find(self.axis_scope.get().split()[0]) if action is not None else None
            if parent is not None:
                node = next((n for n in parent.findall('Axis') if n.get('AxisName') == self.axis_var.get()), None)
                if node is not None:
                    values.update(node.attrib)
        for attr, var in self.axis_values.items():
            var.set(values.get(attr, AXIS_DEFAULTS[attr]))

    def apply_axis(self):
        if not self.profile:
            self.error('Create or open a profile first.')
            return
        try:
            values = {attr: str(int(var.get())) for attr, var in self.axis_values.items()}
            from .profiles import validate_axis
            validate_axis(values)
            action = None
            slot = self.axis_scope.get().split()[0]
            if slot != 'Global':
                if not self.editable():
                    return
                action = self.profile.action(*self.selected)
                if action is None or not self.profile.keys(*self.selected, slot):
                    raise ValueError('Bind this input before applying an override.')
            self.checkpoint()
            self.profile.set_axis(self.axis_var.get(), values, action, slot)
            if action is not None:
                action.set('Flag', str(int(action.get('Flag', '4')) | 4096))
            self.show_action()
            self.status.set(f'{self.axis_var.get()} settings saved to {self.axis_scope.get().lower()}.')
        except ValueError as exc:
            self.error(exc)

    def poll(self):
        if self.controller:
            try:
                current = self.controller.read()
                self.current_values = current
                for obj in self.controller.objects:
                    value = current[obj.offset]
                    text = f'{value:+.3f}' if obj.kind == 'axis' else ('Pressed' if value else 'Released') if obj.kind == 'button' else ('Centered' if value < 0 else f'{value / 100:.0f}°')
                    self.monitor.set(str(obj.offset), 'value', text)
                self.draw_axis()
                if self.capture:
                    capture = self.capture
                    names = changed_inputs(self.controller.objects, capture['baseline'], current, self.split_axes.get())
                    for name in names:
                        if name not in capture['names']:
                            capture['names'].append(name)
                    if names and capture['settle'] is None:
                        capture['settle'] = time.monotonic() + 0.30
                    if capture['settle'] is not None and time.monotonic() >= capture['settle']:
                        self.capture = None
                        pairs = [self.catalogue.resolve(name) for name in capture['names']]
                        if all(pairs):
                            if capture.get('search'):
                                self.input_filter = {str(pair[1]) for pair in pairs}
                                self.refresh_list()
                                self.status.set('Showing bindings using ' + ' + '.join(self.input_display(pair[0]) for pair in pairs) + '. Clear input filter shows all controls.')
                            else:
                                self.bind(capture['slot'], pairs)
                            if self.recording:
                                self.recording['index'] += 1
                                self.recording['waiting'] = True
                                self.recording['stable_since'] = None
                                self.recording['last'] = dict(current)
                                self.status.set('Binding recorded. Release buttons and let the axes settle before the next action.')
                        else:
                            missing = ', '.join(name for name, pair in zip(capture['names'], pairs) if pair is None)
                            self.status.set(f'Detected {missing}; export blocked for this input until its ID is learned from a real XML.')
                            self.error(f'Windows detected: {missing}\n\nNo verified MSFS ID is available for this input. Open a real exported profile containing it. No guessed binding was added.')
                            if self.recording:
                                self.recording['waiting'] = True
                                self.recording['stable_since'] = None
                                self.recording['last'] = dict(current)
                    elif time.monotonic() >= capture['deadline']:
                        self.capture = None
                        self.status.set('No input detected within 12 seconds. Click Get Input to try again.')
                        if self.recording:
                            self.recording['waiting'] = True
                            self.recording['stable_since'] = None
                elif self.recording and self.recording['waiting']:
                    session = self.recording
                    released = all(not current[o.offset] for o in self.controller.objects if o.kind == 'button')
                    hats_centered = all(current[o.offset] < 0 for o in self.controller.objects if o.kind == 'pov')
                    stable = all(abs(current[o.offset] - session['last'].get(o.offset, current[o.offset])) < 0.025
                                 for o in self.controller.objects if o.kind == 'axis')
                    session['last'] = dict(current)
                    if released and hats_centered and stable:
                        if session['stable_since'] is None:
                            session['stable_since'] = time.monotonic()
                        elif time.monotonic() - session['stable_since'] >= .4:
                            self.record_next()
                    else:
                        session['stable_since'] = None
            except OSError as exc:
                self.cancel_capture()
                self.status.set(f'{exc} Reconnect the controller and click Refresh.')
                self.controller.close()
                self.controller = None
        self.root.after(50, self.poll)

    def draw_axis(self):
        obj = next((o for o in self.controller.objects if o.axis == self.axis_var.get()), None)
        canvas = self.axis_canvas
        width = max(100, canvas.winfo_width())
        value = self.current_values.get(obj.offset, 0) if obj else 0
        x = 14 + (width - 28) * (value + 1) / 2
        canvas.delete('all')
        canvas.create_line(14, 43, width - 14, 43, fill='#dce4ef', width=8)
        canvas.create_line(width / 2, 27, width / 2, 58, fill='#93a5ba')
        canvas.create_oval(x - 7, 36, x + 7, 50, fill='#195cf2', outline='')
        canvas.create_text(width / 2, 73, text=f'{self.axis_var.get()}: {value:+.3f}' if obj else 'Axis not present on live controller', fill='#59677b', font=('Segoe UI', 10))

    def save_profile(self):
        if not self.profile:
            self.error('Create or open a profile first.')
            return False
        self.profile.name = self.name_var.get().strip() or 'My flight controls'
        errors = self.profile.validate()
        if errors:
            self.error('\n'.join(errors[:12]))
            return False
        if self.profile.format == 'sdk':
            self.status.set('Saving SDK DefaultInput XML. This format is not verified for Controls-menu import.')
        name = ''.join(c if c not in '<>:"/\\|?*' else '_' for c in self.profile.name)
        path = filedialog.asksaveasfilename(title='Export MSFS 2024 profile', defaultextension='.xml',
                    initialdir=str(self.path.parent) if self.path else None,
                    initialfile=name + '.xml', filetypes=[('XML profile', '*.xml')])
        if not path:
            return False
        try:
            self.profile.save(path)
            sidecar = Path(path).with_suffix('.studio.json')
            guid = self.profile.device.get('GUID', '').lower()
            labels = self.labels.devices.get(guid, {})
            if labels or sidecar.is_file():
                sidecar.write_text(json.dumps({'controller_labels': {guid: labels}}, indent=2), encoding='utf-8')
            self.path, self.saved_text = Path(path), self.profile.to_text()
            self.status.set(f'Exported {self.path.name}. In MSFS: Settings → Controls → this controller → matching profile cogwheel → Import.')
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def import_guide(self):
        messagebox.showinfo('Add the profile to MSFS 2024',
            '1. Export XML to a folder you can find.\n2. Start MSFS 2024 when you are ready to use it.\n3. Settings → Controls → select the same controller.\n4. Click the cogwheel for the matching profile type.\n5. Import → choose your XML → select the imported preset.\n6. Set the desired aircraft/default assignment and test in flight.\n\n'
            'General and airplane controls are separate profiles; export/import each type separately. You can edit every profile with MSFS closed.\n\n'
            'SDK DefaultInput files opened here retain their SDK format; they are not native Controls-menu exports.', parent=self.root)

    def help(self):
        locations = simulator_locations()
        folders = '\n'.join(item['community'] for item in locations) or 'No simulator folder found.'
        messagebox.showinfo('MSFS Input Studio',
            f'Version {__version__} · portable, offline Windows app\n\n'
            'Choose your controller → choose a profile type → find an action → Get Input → Export XML.\n'
            'Use Add to chord for button combinations. Digital repeats while held. Once on press sends one event. Delayed / hold uses Delay in seconds.\n\n'
            f'{len(self.catalogue.actions):,} action/context entries from real exports. Names are readable event IDs, not the simulator’s localized labels. This catalogue is broad but not guaranteed exhaustive. Open additional real exports to extend it.\n\n'
            'Windows inputs without a verified MSFS ID require a real reference export. XInput-only, VR and proprietary controls are not yet validated. CompositeID defaults to 0 for newly detected controllers; use a real export for composite-device metadata.\n\n'
            'The supported delivery route is XML import. Community-package installation needs separate validation and is not enabled. This build has not been tested in MSFS yet.\n\n'
            f'Detected Community folders:\n{folders}', parent=self.root)

    def close(self):
        if not self.can_discard():
            return
        if self.controller:
            self.controller.close()
        if self.backend:
            self.backend.close()
        self.root.destroy()


def run():
    if os.name == 'nt':
        try:
            ctypes.WinDLL('shcore.dll').SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()
