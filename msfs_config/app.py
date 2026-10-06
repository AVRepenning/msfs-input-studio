from copy import deepcopy
import ctypes
import json
import math
import os
import queue
from pathlib import Path
import time
import threading
import uuid
import zlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import __version__
from .catalogue import Catalogue, display_name, normalized, device_family, input_identity
from .devices import DirectInput, changed_inputs
from .locations import simulator_locations
from .labels import ControllerLabels
from .drafts import DraftStore
from .dashboard import ControllerDashboard
from .widgets import ScrollPage
from .conflicts import binding_conflicts
from .system_inputs import SystemController, SystemDevice, XInputController, system_devices
from .profiles import Profile, AXES, AXIS_DEFAULTS, FLAGS

CATEGORIES = {'General controls': 'GENERAL', 'Airplane controls': 'AIRPLANE', 'Helicopter controls': 'HELICOPTER'}
AXIS_LABELS = {'AxisSensitivy': 'Sensitivity +', 'AxisSensitivyMinus': 'Sensitivity −',
               'AxisDeadZone': 'Inner deadzone', 'AxisOutDeadZone': 'Outer deadzone',
               'AxisNeutral': 'Neutral', 'AxisResponseRate': 'Response rate'}


class App:
    def __init__(self, root, user_library=True):
        self.root = root
        self.root.title('MSFS Input Studio')
        self.root.geometry(f'{max(1120, min(1340, root.winfo_screenwidth() - 80))}x{max(680, min(890, root.winfo_screenheight() - 90))}')
        self.root.minsize(1120, 680)
        self.catalogue = Catalogue(storage=user_library)
        self.labels = ControllerLabels(storage=user_library)
        self.profile = None
        self.path = None
        self.saved_text = None
        self.history, self.future = [], []
        self.history_labels, self.future_labels = [], []
        self.backend = None
        self.controller = None
        self.devices = []
        self.current_values = {}
        self.capture = None
        self.recording = None
        self.follow_pending = None
        self.follow_baseline = {}
        self.capture_result = ''
        self.last_capture_slot = 'Primary'
        self.last_capture_search = False
        self.programmatic_selection = None
        self.input_choice_names = {}
        self.selected = None
        self.sort_column, self.sort_reverse = 'name', False
        self.refresh_job = None
        self.reveal_job = None
        self.loading = False
        self.current_profile_category = 'GENERAL'
        self.renaming = False
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
        self.input_filter_names = None
        self.sdk_editors = []
        self.saved_profiles = []
        self.profile_scan_running = False
        self.profile_scan_loaded = False
        self.profile_scan_results = queue.Queue()
        self.profile_scan_cancel = threading.Event()
        self.profile_scan_progress = tk.StringVar(value='Saved profiles have not been scanned yet.')
        self.saved_browser_window = None
        self.saved_browser_refresh = None
        self.user_library = user_library
        self.drafts = DraftStore(storage=user_library)
        self.draft_session = str(uuid.uuid4())
        self.last_draft = None
        self.view_category = tk.StringVar(value='Current profile')
        self.action_group = tk.StringVar(value='All groups')
        self.follow_input = tk.BooleanVar()
        self.unbound_only = tk.BooleanVar()
        self.split_axes = tk.BooleanVar()
        self.capture_mode = tk.StringVar(value='All inputs')
        self.split_pov = tk.BooleanVar(value=True)
        self.record_escape = tk.BooleanVar()
        self.include_modifiers = tk.BooleanVar(value=True)
        self.capture_title = tk.StringVar(value='NOT RECORDING')
        self.capture_detail = tk.StringVar(value='Select an action and click Get Input, or select several actions and Record selected.')
        self.detected_input = tk.StringVar(value='Detected input: —')
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
        self.conflict_detail = tk.StringVar()
        self.label_target = tk.StringVar(value='Select a button, axis scale or input row to name it.')
        self.record_slot = tk.StringVar(value='Primary')
        self.win_keys = ctypes.WinDLL('user32.dll') if os.name == 'nt' else None
        if self.win_keys:
            self.win_keys.GetAsyncKeyState.argtypes = [ctypes.c_int]
            self.win_keys.GetAsyncKeyState.restype = ctypes.c_short
        self._style()
        self._build()
        self.root.report_callback_exception = self.callback_error
        for var in (self.search_var, self.context_var, self.bound_only, self.show_all, self.conflicts_only,
                    self.view_category, self.action_group, self.unbound_only):
            var.trace_add('write', self.schedule_list)
        self.name_var.trace_add('write', self.rename_profile)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        for sequence, command in [('<Control-o>', self.open_profile), ('<Control-s>', self.save_profile),
                                  ('<Control-z>', self.undo), ('<Control-y>', self.redo)]:
            self.root.bind(sequence, lambda event, cmd=command: self.shortcut(cmd))
        self.root.bind('<Escape>', self.escape)
        self.root.bind('<MouseWheel>', self.capture_wheel, add='+')
        self.root.after(3000, self.autosave_draft)
        self.root.after(80, self.refresh_devices)
        self.root.after(150, self.poll)
        if user_library:
            self.root.after(600, lambda: self.scan_saved_profiles(quiet=True))
        self.refresh_list()

    def _style(self):
        self.root.configure(bg='#edf1f5')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#edf1f5', foreground='#243247')
        style.configure('TButton', padding=(10, 7))
        style.configure('Accent.TButton', background='#195cf2', foreground='white')
        style.map('Accent.TButton', background=[('disabled', '#e0e5ec'), ('active', '#1549c0')],
                  foreground=[('disabled', '#7b8796')])
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
        ttk.Button(header, text='Import guide', command=self.import_guide).pack(side='right')
        ttk.Button(header, text='Help', command=self.help).pack(side='right', padx=6)
        ttk.Button(header, text='Test controller', command=self.controller_test_window).pack(side='right', padx=6)
        ttk.Button(header, text='Tools', command=self.tools_menu).pack(side='right')
        ttk.Button(header, text='Guided setup', command=self.guided_setup).pack(side='right', padx=6)

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
        self.name_entry = ttk.Entry(toolbar, textvariable=self.name_var, width=25)
        self.name_entry.pack(side='left')
        self.name_entry.bind('<FocusOut>', lambda _: setattr(self, 'renaming', False))
        self.category_combo = ttk.Combobox(toolbar, textvariable=self.type_var, values=list(CATEGORIES), state='readonly', width=20)
        self.category_combo.pack(side='left', padx=8)
        self.category_combo.bind('<<ComboboxSelected>>', self.category_changed)
        for label, command in [('New', self.new_profile_dialog), ('Open XML', self.open_profile),
                               ('Duplicate', self.duplicate), ('Undo', self.undo), ('Redo', self.redo)]:
            ttk.Button(toolbar, text=label, command=command).pack(side='left', padx=2)
        ttk.Button(toolbar, text='Export XML', style='Accent.TButton', command=self.save_profile).pack(side='right')
        ttk.Button(toolbar, text='Saved', command=self.saved_profile_browser).pack(side='left', padx=5)

        self.capture_panel = tk.Frame(shell, bg='#e4eaf1', padx=12, pady=8)
        self.capture_panel.pack(fill='x', pady=(0, 12))
        self.retry_button = ttk.Button(self.capture_panel, text='Try again', command=self.retry_capture, state='disabled')
        self.retry_button.pack(side='right', padx=(10, 0))
        self.continue_button = ttk.Button(self.capture_panel, text='Continue anyway', command=self.record_next, state='disabled')
        self.continue_button.pack(side='right')
        self.panel_cancel = ttk.Button(self.capture_panel, text='Stop listening', command=self.cancel_capture)
        self.capture_heading = tk.Label(self.capture_panel, textvariable=self.capture_title,
                                        bg='#e4eaf1', fg='#33445b', font=('Segoe UI', 11, 'bold'), anchor='w')
        self.capture_heading.pack(fill='x')
        self.capture_description = tk.Label(self.capture_panel, textvariable=self.capture_detail,
                                            bg='#e4eaf1', fg='#33445b', font=('Segoe UI', 10), anchor='w', wraplength=1020)
        self.capture_description.pack(fill='x', pady=2)
        self.capture_detected = tk.Label(self.capture_panel, textvariable=self.detected_input,
                                        bg='#e4eaf1', fg='#33445b', font=('Segoe UI', 10), anchor='w', wraplength=1020)
        self.capture_detected.pack(fill='x')

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
        ttk.Label(filters, text='Show').pack(side='left', padx=(0, 5))
        ttk.Combobox(filters, textvariable=self.view_category, state='readonly', width=18,
                     values=['Current profile', 'All controls'] + list(CATEGORIES)).pack(side='left', padx=(0, 8))
        self.context_combo = ttk.Combobox(filters, textvariable=self.context_var, state='readonly', width=25,
                                        values=['All contexts'] + sorted({a[0] for a in self.catalogue.actions}))
        self.context_combo.pack(side='left', fill='x', expand=True)
        groups = ttk.Frame(left)
        groups.pack(fill='x', pady=(0, 7))
        self.group_combo = ttk.Combobox(groups, textvariable=self.action_group, state='readonly', width=23,
                                       values=['All groups'])
        self.group_combo.pack(side='left')
        filters = groups
        ttk.Checkbutton(filters, text='Bound only', variable=self.bound_only).pack(side='left', padx=8)
        ttk.Checkbutton(filters, text='Unbound', variable=self.unbound_only).pack(side='left')
        ttk.Checkbutton(filters, text='Conflicts', variable=self.conflicts_only).pack(side='left', padx=5)
        recording_row = ttk.Frame(left)
        recording_row.pack(fill='x', pady=(0, 7))
        self.record_button = ttk.Button(recording_row, text='Record selected', style='Accent.TButton', command=self.record_selected)
        self.record_button.pack(side='left')
        ttk.Combobox(recording_row, textvariable=self.record_slot, values=['Primary', 'Secondary'], state='readonly', width=11).pack(side='left', padx=5)
        self.skip_button = ttk.Button(recording_row, text='Skip', command=self.skip_recording, state='disabled')
        self.skip_button.pack(side='left')
        self.stop_button = ttk.Button(recording_row, text='Stop', command=self.stop_recording, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        recording_row = ttk.Frame(left)
        recording_row.pack(fill='x', pady=(0, 7))
        ttk.Button(recording_row, text='Find input', command=self.find_input).pack(side='left')
        ttk.Button(recording_row, text='Clear input filter', command=self.clear_input_filter).pack(side='left', padx=5)
        ttk.Checkbutton(recording_row, text='Follow controller', variable=self.follow_input,
                        command=self.toggle_follow).pack(side='left')
        ttk.Button(recording_row, text='Edit selected…', command=self.selected_actions_menu).pack(side='right')
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
        self.empty_results = ttk.Frame(table, padding=20)
        self.empty_results_title = ttk.Label(self.empty_results, text='No controls shown', style='Heading.TLabel')
        self.empty_results_title.pack(anchor='w')
        self.empty_results_detail = ttk.Label(self.empty_results, wraplength=580)
        self.empty_results_detail.pack(anchor='w', pady=(8, 12))
        self.empty_results.bind('<Configure>', lambda event: self.empty_results_detail.configure(wraplength=max(240, event.width - 40)))
        self.show_other_profiles_button = ttk.Button(self.empty_results, text='Show matching controls from all profiles',
                                                     command=self.show_matching_controls, style='Accent.TButton')
        self.clear_filters_button = ttk.Button(self.empty_results, text='Clear filters', command=self.clear_browse_filters)
        self.clear_filters_button.pack(anchor='w')
        self.tree.tag_configure('unavailable', foreground='#919aaa')
        self.tree.tag_configure('bound', foreground='#185ba8')
        self.tree.tag_configure('conflict', foreground='#9c3e09')
        self.tree.bind('<<TreeviewSelect>>', self.select_action)
        self.tree.bind('<Button-3>', self.selected_actions_menu)
        self.count_label = ttk.Label(left, text='', style='Muted.TLabel', wraplength=660)
        self.count_label.pack(before=table, side='bottom', fill='x', pady=7, anchor='w')

        self.action_title = ttk.Label(right, text='Select a control', style='Heading.TLabel', wraplength=445)
        self.action_title.pack(anchor='w')
        self.action_id = ttk.Label(right, text='Search by name, event ID or context.', style='Muted.TLabel', wraplength=440)
        self.action_id.pack(anchor='w', pady=(5, 12))
        self.profile_hint = ttk.Frame(right, padding=(0, 0, 0, 10))
        self.profile_hint_text = ttk.Label(self.profile_hint, wraplength=430, foreground='#9c3e09')
        self.profile_hint_text.pack(fill='x')
        self.profile_hint_button = ttk.Button(self.profile_hint, command=self.use_selected_profile_type)
        self.profile_hint_button.pack(anchor='w', pady=(6, 0))
        tabs = self.tabs = ttk.Notebook(right)
        tabs.pack(fill='both', expand=True)
        pages = [ScrollPage(tabs) for _ in range(3)]
        binding_page, behavior_page, axis_page = [page.content for page in pages]
        monitor_page = ttk.Frame(tabs, padding=12)
        for page, title in zip(pages, ('Bindings', 'Behavior', 'Axis tuning')):
            tabs.add(page, text=title)
        tabs.add(monitor_page, text='Live inputs')
        self.monitor_page = monitor_page
        self.input_combos = {}
        self.binding_buttons = []
        for slot in self.slot_vars:
            card = ttk.LabelFrame(binding_page, text=slot)
            card.pack(fill='x', pady=(0, 10))
            ttk.Label(card, textvariable=self.slot_vars[slot], wraplength=410).pack(fill='x', pady=(0, 8))
            combo = ttk.Combobox(card, textvariable=self.input_vars[slot], state='readonly')
            combo.pack(fill='x')
            self.input_combos[slot] = combo
            buttons = ttk.Frame(card)
            buttons.pack(fill='x', pady=(7, 0))
            for label, cmd in [('Get Input', lambda s=slot: self.start_capture(s)),
                               ('Use', lambda s=slot: self.manual_binding(s)),
                               ('Add to chord', lambda s=slot: self.manual_binding(s, True)),
                               ('Clear', lambda s=slot: self.clear_binding(s))]:
                button = ttk.Button(buttons, text=label, command=cmd, width=0, state='disabled',
                                    style='Accent.TButton' if label == 'Get Input' else 'TButton')
                button.pack(side='left', fill='x', expand=True, padx=(0, 3))
                self.binding_buttons.append((slot, label, button))
        capture_row = ttk.Frame(binding_page)
        capture_row.pack(fill='x')
        ttk.Checkbutton(capture_row, text='Split axes (+ / −)', variable=self.split_axes).pack(side='left')
        ttk.Checkbutton(capture_row, text='Split hats', variable=self.split_pov).pack(side='left', padx=5)
        self.cancel_button = ttk.Button(capture_row, text='Cancel', command=self.cancel_capture, state='disabled')
        self.cancel_button.pack(side='right')
        ttk.Checkbutton(binding_page, text='Allow recording Escape (use Cancel to stop)', variable=self.record_escape).pack(anchor='w', pady=(8, 0))
        ttk.Checkbutton(binding_page, text='Include Ctrl / Shift / Alt while recording', variable=self.include_modifiers).pack(anchor='w', pady=5)
        ttk.Label(binding_page, text='Listen to').pack(anchor='w', pady=(5, 0))
        ttk.Combobox(binding_page, textvariable=self.capture_mode, state='readonly',
                     values=['All inputs', 'Buttons / keys only', 'Axes only', 'Hats only']).pack(fill='x', pady=4)
        ttk.Label(binding_page, textvariable=self.conflict_detail, wraplength=430, foreground='#9c3e09').pack(fill='x', pady=(12, 0))
        ttk.Label(behavior_page, text='Digital repeats while held. Once on press sends a single event. On release triggers when you release the button.',
                  style='Muted.TLabel', wraplength=415).pack(anchor='w', pady=(0, 12))
        options = ttk.LabelFrame(behavior_page, text='Action behavior', padding=8)
        options.pack(fill='x', pady=(9, 0))
        for index, (bit, label) in enumerate(FLAGS.items()):
            ttk.Checkbutton(options, text=label, variable=self.flag_vars[bit], command=self.flags_changed).grid(
                row=index // 2, column=index % 2, sticky='w', padx=3, pady=2)
        fields = ttk.Frame(options)
        fields.grid(row=8, column=0, columnspan=2, sticky='ew', pady=7)
        for label, var in [('Flags', self.flag_value), ('Value', self.event_value), ('Delay (s)', self.delay_value)]:
            ttk.Label(fields, text=label).pack(side='left', padx=(0, 4))
            ttk.Entry(fields, textvariable=var, width=8).pack(side='left', padx=(0, 8))
        ttk.Button(options, text='Apply behavior', command=self.apply_behavior).grid(row=9, column=0, columnspan=2, sticky='ew')

        ttk.Label(axis_page, text='Axis settings are saved to the profile.', style='Muted.TLabel', wraplength=420).pack(anchor='w')
        row = ttk.Frame(axis_page)
        row.pack(fill='x', pady=10)
        self.axis_combo = ttk.Combobox(row, textvariable=self.axis_var, values=AXES, width=11, state='readonly')
        self.axis_combo.pack(side='left')
        self.axis_combo.bind('<<ComboboxSelected>>', lambda _: self.load_axis())
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
            ttk.Scale(row, from_=low, to=high, variable=self.axis_values[attr],
                      command=lambda value, name=attr: self.axis_values[name].set(str(round(float(value))))).pack(side='left', fill='x', expand=True, padx=(10, 0))
        ttk.Label(axis_page, text='Sensitivity / neutral: −100 to 100. Deadzones: 0–100.\nResponse rate: −1 for default, or 100–2000.', style='Muted.TLabel').pack(anchor='w', pady=10)
        ttk.Button(axis_page, text='Apply axis settings', style='Accent.TButton', command=self.apply_axis).pack(fill='x', pady=8)
        ttk.Button(axis_page, text='Reset these axis settings', command=self.reset_axis).pack(fill='x')
        ttk.Label(axis_page, text='Live axis position', style='Heading.TLabel').pack(anchor='w', pady=(15, 5))
        self.axis_canvas = tk.Canvas(axis_page, height=90, bg='white', highlightthickness=0)
        self.axis_canvas.pack(fill='x')
        ttk.Label(axis_page, text='This shows raw controller input. MSFS applies the saved sensitivity curve during flight.', style='Muted.TLabel', wraplength=410).pack(anchor='w', pady=8)

        ttk.Label(monitor_page, textvariable=self.monitor_status, wraplength=420, style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        ttk.Label(monitor_page, text='Click a light or scale to name it. Red means pressed.', style='Muted.TLabel', wraplength=420).pack(anchor='w', pady=(0, 5))
        naming = ttk.Frame(monitor_page)
        naming.pack(fill='x', pady=(0, 10))
        ttk.Entry(naming, textvariable=self.input_label_var, width=24).pack(side='left', fill='x', expand=True)
        ttk.Button(naming, text='Set name', command=self.set_input_label).pack(side='left', padx=4)
        ttk.Button(naming, text='Reset', command=lambda: self.set_input_label(reset=True)).pack(side='left')
        monitor_tabs = ttk.Notebook(monitor_page)
        monitor_tabs.pack(fill='both', expand=True)
        self.dashboard = ControllerDashboard(monitor_tabs, self.select_dashboard_input, self.object_label, compact=True)
        monitor_tabs.add(self.dashboard, text='Controller test')
        input_list = ttk.Frame(monitor_tabs)
        monitor_tabs.add(input_list, text='Input names / IDs')
        self.monitor = ttk.Treeview(input_list, columns=('input', 'value', 'support'), show='headings', height=10)
        for column, title, width in [('input', 'Windows input', 160), ('value', 'Value', 70), ('support', 'XML ID', 95)]:
            self.monitor.heading(column, text=title)
            self.monitor.column(column, width=width, minwidth=50)
        scroll = ttk.Scrollbar(input_list, orient='vertical', command=self.monitor.yview)
        self.monitor.configure(yscrollcommand=scroll.set)
        self.monitor.pack(side='left', fill='both', expand=True)
        self.monitor.bind('<<TreeviewSelect>>', self.select_monitor_input)
        scroll.pack(side='right', fill='y')
        ttk.Label(shell, textvariable=self.status, wraplength=1250, style='Muted.TLabel').pack(
            before=body, side='bottom', fill='x', pady=(12, 0))

    def error(self, exc):
        self.cancel_capture()
        self.feedback('ERROR · NOT RECORDING', str(exc), 'error')
        messagebox.showerror('MSFS Input Studio', str(exc), parent=self.root)

    def callback_error(self, kind, value, traceback_object):
        import traceback
        directory = Path(os.environ.get('LOCALAPPDATA', '.')) / 'MSFSInputStudio'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'error.log').write_text(''.join(traceback.format_exception(kind, value, traceback_object)), encoding='utf-8')
        self.error(f'An app command failed: {value}\nDetails: {directory / "error.log"}')

    def feedback(self, title, detail, kind='idle', detected=None):
        colors = {'idle': ('#e4eaf1', '#33445b'), 'listen': ('#fff0cf', '#795100'),
                  'success': ('#dff2e7', '#14693c'), 'error': ('#fbe0e3', '#941d32'),
                  'search': ('#e0edff', '#174d96')}
        bg, fg = colors[kind]
        self.capture_title.set(title)
        self.capture_detail.set(detail)
        if detected is not None:
            self.detected_input.set('Detected input: ' + (detected or '—'))
            if detected:
                self.capture_detected.pack(fill='x')
            else:
                self.capture_detected.pack_forget()
        self.capture_panel.configure(bg=bg)
        for widget in (self.capture_heading, self.capture_description, self.capture_detected):
            widget.configure(bg=bg, fg=fg)
        active = bool(self.capture or self.recording or self.follow_input.get())
        if active:
            self.panel_cancel.pack(before=self.capture_heading, side='right', padx=(10, 0))
        else:
            self.panel_cancel.pack_forget()
        self.root.capturing_mouse = bool(active and self.profile and device_family(self.profile.device.attrib) == 'mouse')
        self.cancel_button.configure(state='normal' if active else 'disabled')
        self.skip_button.configure(state='normal' if self.recording else 'disabled')
        self.stop_button.configure(state='normal' if self.recording else 'disabled')
        self.retry_button.configure(state='disabled' if self.capture else 'normal' if self.capture_result == 'retry' else 'disabled')
        self.continue_button.configure(state='normal' if self.recording and self.recording['waiting'] else 'disabled')
        if self.capture_result == 'retry' and not self.capture:
            self.retry_button.pack(before=self.capture_heading, side='right', padx=(10, 0))
        else:
            self.retry_button.pack_forget()
        if self.recording and self.recording['waiting']:
            self.continue_button.pack(before=self.capture_heading, side='right')
        else:
            self.continue_button.pack_forget()
        controls = (self.panel_cancel, self.retry_button, self.continue_button)
        width = max(350, self.capture_panel.winfo_width() - 30 - sum(widget.winfo_reqwidth() + 10 for widget in controls if widget.winfo_manager()))
        self.capture_description.configure(wraplength=width)
        self.capture_detected.configure(wraplength=width)
        self.schedule_reveal()

    def schedule_reveal(self):
        if self.reveal_job is None and self.selected:
            self.reveal_job = self.root.after_idle(self.reveal_selected)

    def reveal_selected(self):
        self.reveal_job = None
        row = next((row for row, identity in self.row_ids.items() if identity == self.selected), None)
        if row is not None:
            self.tree.see(row)

    def object_label(self, obj):
        device = self.selected_device()
        label = self.labels.get(self.label_guid(device.attributes), obj.msfs_name()) if device else ''
        return f'{label} · {obj.axis or obj.index + 1}' if label else self.default_input_label(obj)

    @staticmethod
    def default_input_label(obj):
        return f'Button {obj.index + 1}' if obj.kind == 'button' and not getattr(obj, 'family', '') else obj.name

    def resolve_input(self, name):
        family = device_family(self.profile.device.attrib) if self.profile else 'joystick'
        return self.catalogue.resolve(name, family)

    @staticmethod
    def label_guid(attributes):
        guid = attributes.get('GUID', '')
        return guid + ':' + device_family(attributes) if guid == '{0}' else guid

    def controller_matches(self):
        return bool(self.controller and self.profile and
                    self.profile.device.get('GUID', '').lower() == self.controller.device.instance_guid.lower() and
                    device_family(self.profile.device.attrib) == device_family(self.controller.device.attributes))

    def select_profile_controller(self):
        if not self.profile or self.controller_matches():
            return
        for index, device in enumerate(self.devices):
            if device.instance_guid.lower() == self.profile.device.get('GUID', '').lower() and device_family(device.attributes) == device_family(self.profile.device.attrib):
                self.device_combo.current(index)
                self.select_device()
                return

    def keyboard_modifiers(self):
        if not self.win_keys or not self.include_modifiers.get():
            return 0
        return sum(bit for vk, bit in ((17, 16), (16, 32), (18, 64)) if self.win_keys.GetAsyncKeyState(vk) & 0x8000)

    def shortcut(self, command):
        if not self.capture and not self.recording and not self.follow_input.get():
            command()
        return 'break'

    def escape(self, _=None):
        if self.record_escape.get() and self.capture and self.profile and device_family(self.profile.device.attrib) == 'keyboard':
            return 'break'
        self.cancel_capture()
        return 'break'

    def capture_wheel(self, event):
        if isinstance(self.controller, SystemController) and self.controller.device.family == 'mouse' and (self.capture or self.follow_input.get()):
            self.controller.wheel(event.delta)
            return 'break'

    def select_dashboard_input(self, obj):
        self.monitor.selection_set(str(obj.offset))
        self.monitor.see(str(obj.offset))
        self.select_monitor_input()
        self.status.set(f'Selected {obj.name}. Enter a name above the controller test, then Set name.')

    def controller_test_window(self):
        window = tk.Toplevel(self.root)
        window.title('Controller test and input names')
        window.geometry(f'760x{max(650, min(880, self.root.winfo_screenheight() - 90))}')
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, textvariable=self.device_var, style='Heading.TLabel', wraplength=710).pack(anchor='w')
        ttk.Label(frame, text='Move every axis and press each button. Click an input to give it a useful name.', wraplength=710).pack(anchor='w', pady=8)
        ttk.Label(frame, textvariable=self.label_target, style='Muted.TLabel').pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=8)
        ttk.Entry(row, textvariable=self.input_label_var).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Set name', command=self.set_input_label).pack(side='left', padx=6)
        ttk.Button(row, text='Reset name', command=lambda: self.set_input_label(reset=True)).pack(side='left')
        dashboard = ControllerDashboard(frame, self.select_dashboard_input, self.object_label)
        dashboard.pack(fill='both', expand=True)
        def refresh():
            if window.winfo_exists():
                dashboard.selected_offset = self.dashboard.selected_offset
                dashboard.update_inputs(self.controller.objects if self.controller else [], self.current_values if self.controller else {})
                window.after(100, refresh)
        refresh()
        return window, dashboard

    def checkpoint(self, description='Edit profile'):
        if self.profile:
            self.history.append(self.snapshot())
            self.history_labels.append(description)
            self.future.clear()
            self.future_labels.clear()
            self.renaming = False

    def snapshot(self):
        return zlib.compress(self.profile.to_text().encode('utf-8'))

    def autosave_draft(self):
        try:
            self.save_draft()
        except (OSError, ValueError) as exc:
            self.status.set(f'Could not save the local working copy: {exc}. Export XML to save your work.')
        finally:
            self.root.after(3000, self.autosave_draft)

    def save_draft(self):
        if self.drafts.folder and self.profile and (self.dirty() or self.last_draft is not None):
            text = self.profile.to_text()
            if text != self.last_draft:
                guid = self.label_guid(self.profile.device.attrib).lower()
                self.drafts.save(self.draft_session, self.profile, {guid: self.labels.devices.get(guid, {})})
                self.last_draft = text

    def draft_browser(self):
        rows = self.drafts.entries()
        window = tk.Toplevel(self.root)
        window.title('Local working copies')
        window.geometry('800x490')
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Resume a profile you were working on', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Edits are saved here automatically every three seconds. These are local working copies; Export XML creates a file to import in MSFS.', wraplength=740).pack(anchor='w', pady=10)
        listing = tk.Listbox(frame, height=15, exportselection=False)
        listing.pack(fill='both', expand=True)
        for row in rows:
            profile = row['profile']
            listing.insert('end', f'{profile.name} · {profile.category} · {profile.device.get("DeviceName")} · {row["updated"][:16].replace("T", " ")} UTC')
        if rows:
            listing.selection_set(0)
        else:
            listing.insert('end', 'No working copies yet. Record or edit a profile to create one.')
        def open_copy(_=None):
            selection = listing.curselection()
            if not rows or not selection or not self.can_discard():
                return
            row = rows[selection[0]]
            self.cancel_capture()
            self.profile = Profile.from_text(row['profile'].to_text())
            self.catalogue.learn(self.profile)
            self.catalogue.save_library()
            self.labels.merge(row['labels'])
            self.labels.save()
            self.path, self.saved_text = None, self.profile.to_text()
            self.draft_session, self.last_draft = row['id'], self.profile.to_text()
            self.history, self.future, self.history_labels, self.future_labels = [], [], [], []
            self.selected = None
            self.clear_browse_filters()
            self.sync_profile()
            self.refresh_devices()
            self.select_profile_controller()
            self.feedback('WORKING COPY OPENED · NOT RECORDING', 'Continue editing, then Export XML and import it through MSFS Controls.', 'success')
            window.destroy()
        listing.bind('<Double-1>', open_copy)
        ttk.Button(frame, text='Open selected working copy', command=open_copy, style='Accent.TButton').pack(fill='x', pady=(12, 0))
        return window

    def dirty(self):
        return self.profile is not None and self.profile.to_text() != self.saved_text

    def can_discard(self):
        try:
            self.save_draft()
        except (OSError, ValueError) as exc:
            self.status.set(f'Could not save the working copy: {exc}')
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
            references = [row['profile'] for row in self.saved_profiles] + ([self.profile] if self.profile else [])
            self.devices.extend(system_devices(references, self.catalogue))
            names = [d.name if isinstance(d, SystemDevice) else f'{d.name}  [{d.instance_guid[1:9]}]' for d in self.devices]
            self.device_combo.configure(values=names)
            if names:
                self.device_var.set(previous if previous in names else names[0])
                self.select_device()
            else:
                self.device_var.set('No game controllers detected')
                self.device_summary.configure(text='Plug in a controller, then Refresh.')
                self.monitor_status.set('Offline editing is available through Open XML.')
                self.monitor.delete(*self.monitor.get_children())
                self.dashboard.update_inputs([], {})
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
            self.controller = (XInputController(device) if device.family == 'gamepad' else SystemController(device)) if isinstance(device, SystemDevice) else self.backend.open(device, hwnd)
            self.current_values = self.controller.read()
            self.follow_baseline = dict(self.current_values)
            self.dashboard.update_inputs(self.controller.objects, self.current_values)
            counts = [sum(o.kind == kind for o in device.objects) for kind in ('axis', 'button', 'pov')]
            self.device_summary.configure(text=f'{counts[0]} axes · {counts[1]} buttons · {counts[2]} hats')
            self.monitor_status.set(f'{counts[0]} axes · {counts[1]} buttons / keys · {counts[2]} hats · connected')
            self.monitor.delete(*self.monitor.get_children())
            for obj in device.objects:
                family = device_family(device.attributes)
                pair = self.catalogue.resolve(obj.msfs_name(), family) if obj.kind != 'pov' else self.catalogue.resolve(obj.msfs_name('Up'), family)
                label = self.labels.get(self.label_guid(device.attributes), obj.msfs_name()) or self.default_input_label(obj)
                self.monitor.insert('', 'end', iid=str(obj.offset), values=(label, '—', str(pair[1]) if pair else 'Needs reference'))
            self.update_input_choices()
            if self.profile is None:
                self.new_profile()
            elif not self.controller_matches():
                self.status.set('Live controller differs from the profile. Use for this profile to transfer it explicitly.')
            self.update_binding_buttons()
        except Exception as exc:
            self.device_summary.configure(text='Cannot read controller')
            self.status.set(str(exc))

    def update_input_choices(self):
        choices = set()
        device = self.selected_device()
        if device and device.objects and (not self.profile or self.controller_matches()):
            from .devices import POV_DIRECTIONS
            for obj in device.objects:
                candidates = ([obj.msfs_name(d) for d in POV_DIRECTIONS] if obj.kind == 'pov' else
                              [obj.msfs_name(d) for d in ('', '+', '-')] if obj.kind == 'axis' else [obj.msfs_name()])
                for name in candidates:
                    pair = self.resolve_input(name)
                    choices.add(pair[0] if pair else name + ' [needs reference]')
        else:
            family = device_family(self.profile.device.attrib) if self.profile else 'joystick'
            choices = set(self.catalogue.keys_for(family))
        guid = self.label_guid(self.profile.device.attrib) if self.profile else self.label_guid(device.attributes) if device else ''
        self.input_choice_names = {}
        for name in choices:
            label = self.labels.get(guid, name.removesuffix(' [needs reference]'))
            rendered = f'{label} · {name}' if label else name
            self.input_choice_names[rendered] = name
        for combo in self.input_combos.values():
            combo.configure(values=sorted(self.input_choice_names))
        family = device_family(self.profile.device.attrib) if self.profile else 'joystick'
        for slot, var in self.input_vars.items():
            keys = self.profile.keys(*self.selected, slot) if self.profile and self.selected else []
            raw = keys[0][0] if keys else ''
            var.set(next((rendered for rendered, name in self.input_choice_names.items() if input_identity(name, family) == input_identity(raw, family)), ''))

    def input_display(self, name, guid=None):
        if guid is None:
            guid = self.label_guid(self.profile.device.attrib) if self.profile else ''
        label = self.labels.get(guid, name)
        if not label and self.controller_matches() and device_family(self.profile.device.attrib) == 'keyboard':
            obj = next((obj for obj in self.controller.objects if input_identity(obj.msfs_name(), 'keyboard') == input_identity(name, 'keyboard')), None)
            label = obj.name if obj and obj.name.strip().casefold() != name.strip().casefold() else ''
        return f'{label} ({name.strip()})' if label else name.strip()

    def select_monitor_input(self, _=None):
        selected = self.monitor.selection()
        device = self.selected_device()
        if selected and device:
            obj = next((o for o in device.objects if str(o.offset) == selected[0]), None)
            if obj:
                self.input_label_var.set(self.labels.get(self.label_guid(device.attributes), obj.msfs_name()) or self.default_input_label(obj))
                self.label_target.set('Naming: ' + self.default_input_label(obj))
                self.monitor_status.set(self.label_target.get())
                self.dashboard.selected_offset = obj.offset
                self.dashboard.draw()

    def set_input_label(self, reset=False):
        selected = self.monitor.selection()
        device = self.selected_device()
        if not selected or not device:
            self.error('Select an input in Live inputs first.')
            return
        obj = next(o for o in device.objects if str(o.offset) == selected[0])
        try:
            self.labels.set(self.label_guid(device.attributes), obj.msfs_name(), '' if reset else self.input_label_var.get())
            label = self.labels.get(self.label_guid(device.attributes), obj.msfs_name()) or self.default_input_label(obj)
            self.monitor.set(selected[0], 'input', label)
            self.input_label_var.set(label)
            self.update_input_choices()
            self.refresh_list()
            self.show_action()
            self.status.set(f'Input named {label}. Its original MSFS input name and ID are unchanged.')
            self.dashboard.draw()
        except (OSError, ValueError) as exc:
            self.error(exc)

    def new_profile_dialog(self, preferred_category=None):
        window = tk.Toplevel(self.root)
        window.title('Create a profile')
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Choose what you want to configure', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='General, airplane and helicopter controls are separate simulator profiles. Your current profile is kept until you create the new one.', wraplength=450).pack(anchor='w', pady=10)
        name = tk.StringVar(value='My flight controls')
        category = tk.StringVar(value=next((label for label, value in CATEGORIES.items() if value == preferred_category),
                                          self.type_var.get() if self.type_var.get() in CATEGORIES else 'General controls'))
        ttk.Label(frame, text='Profile name').pack(anchor='w')
        entry = ttk.Entry(frame, textvariable=name)
        entry.pack(fill='x', pady=(4, 10))
        ttk.Combobox(frame, textvariable=category, values=list(CATEGORIES), state='readonly').pack(fill='x')
        def create():
            previous = self.profile
            self.new_profile(name.get(), CATEGORIES[category.get()])
            if self.profile is not previous:
                window.destroy()
        ttk.Button(frame, text='Create profile', command=create, style='Accent.TButton').pack(fill='x', pady=(15, 0))
        entry.focus_set()
        entry.selection_range(0, 'end')
        window.bind('<Return>', lambda _: create())

    def new_profile(self, name=None, category=None):
        device = self.selected_device()
        if not device and not self.profile:
            self.error('Connect a Windows controller, then Refresh, or open an exported XML profile.')
            return
        if not self.can_discard():
            return
        identity = device.attributes if device else dict(self.profile.device.attrib)
        axes = [o.axis for o in device.objects if o.kind == 'axis'] if device else [a.get('AxisName') for a in self.profile.device.findall('Axes/Axis')]
        self.profile = Profile.new((name or self.name_var.get()).strip() or 'My flight controls', identity,
                                   category or CATEGORIES[self.type_var.get()], axes)
        self.loading = True
        self.name_var.set(self.profile.name)
        self.type_var.set(next(label for label, value in CATEGORIES.items() if value == self.profile.category))
        self.loading = False
        self.path, self.saved_text = None, self.profile.to_text()
        self.draft_session, self.last_draft = str(uuid.uuid4()), None
        self.history, self.future = [], []
        self.history_labels, self.future_labels = [], []
        self.current_profile_category = self.profile.category
        self.selected = None
        self.action_title.configure(text='Select a control')
        self.cancel_capture()
        self.clear_browse_filters()
        self.action_id.configure(text='Search by name, event ID or context.')
        for slot in self.slot_vars:
            self.slot_keys[slot] = []
            self.slot_vars[slot].set('Unbound')
        self.refresh_list()
        self.load_axis()
        self.status.set('New profile. Choose a control, then click Get Input or choose a Windows input.')
        self.update_binding_buttons()

    def open_profile(self):
        self.cancel_capture()
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
            self.draft_session, self.last_draft = str(uuid.uuid4()), None
            sidecar = self.path.with_suffix('.studio.json')
            if sidecar.is_file() and sidecar.stat().st_size < 1_000_000:
                try:
                    self.labels.merge(json.loads(sidecar.read_text(encoding='utf-8')).get('controller_labels', {}))
                    self.labels.save()
                except (OSError, ValueError, TypeError) as exc:
                    self.status.set(f'Profile opened; could not load its input labels: {exc}')
            self.saved_text = profile.to_text()
            self.history, self.future = [], []
            self.history_labels, self.future_labels = [], []
            self.sync_profile()
            self.update_input_choices()
            self.refresh_devices()
            self.select_profile_controller()
            self.context_combo.configure(values=['All contexts'] + sorted({a[0] for a in self.catalogue.actions}))
            self.status.set(f'Opened {self.path.name} · {profile.device.get("DeviceName")} · {profile.format} XML')
        except Exception as exc:
            self.error(exc)

    def sync_profile(self):
        self.loading = True
        self.name_var.set(self.profile.name)
        self.type_var.set(next((label for label, value in CATEGORIES.items() if value == self.profile.category), self.profile.category + ' controls'))
        self.current_profile_category = self.profile.category
        self.loading = False
        self.category_combo.configure(state='readonly')
        self.refresh_list()
        self.show_action()
        self.load_axis()
        self.update_input_choices()

    def rename_profile(self, *_):
        if not self.loading and self.profile:
            if not self.renaming:
                self.checkpoint('Rename profile')
                self.renaming = True
            self.profile.name = self.name_var.get()

    def category_changed(self, _=None):
        chosen = CATEGORIES.get(self.type_var.get())
        if self.profile:
            self.type_var.set(next((label for label, value in CATEGORIES.items() if value == self.profile.category),
                                   self.profile.category + ' controls'))
        if chosen and (not self.profile or chosen != self.profile.category):
            self.use_profile_type(chosen)

    def use_profile_type(self, chosen):
        if self.profile and self.profile.can_change_category():
            self.cancel_capture()
            self.checkpoint('Change profile type')
            self.profile.change_empty_category(chosen)
            self.sync_profile()
            label = next(label for label, value in CATEGORIES.items() if value == chosen)
            self.feedback('PROFILE TYPE UPDATED · NOT RECORDING',
                          f'{label}. Your profile name, controller and axis settings are kept. Select a control and click Get Input.', 'success')
        else:
            self.new_profile_dialog(chosen)

    def selected_profile_type(self):
        categories = self.catalogue.actions[self.selected]['categories'] if self.selected else []
        return next((value for value in CATEGORIES.values() if value in categories), None)

    def use_selected_profile_type(self):
        chosen = self.selected_profile_type()
        if chosen:
            self.use_profile_type(chosen)

    def duplicate(self):
        if not self.profile:
            return
        try:
            self.save_draft()
        except (OSError, ValueError) as exc:
            self.status.set(f'Could not save the original working copy: {exc}')
        self.checkpoint('Duplicate profile')
        self.draft_session, self.last_draft = str(uuid.uuid4()), None
        self.profile.name = self.profile.name + ' copy'
        self.path = None
        self.sync_profile()
        self.status.set('Duplicated. Export XML to save the copy as a new file.')

    def retarget(self):
        device = self.selected_device()
        if not self.profile or not device:
            return
        if device_family(self.profile.device.attrib) != device_family(device.attributes):
            self.error('Keyboard, mouse, gamepad and joystick input IDs belong to different formats. Click New to create a profile for this device.')
            return
        self.cancel_capture()
        self.checkpoint('Transfer to controller')
        original_guid = self.label_guid(self.profile.device.attrib).lower()
        inherited = self.labels.devices.get(original_guid, {})
        if inherited:
            target = self.labels.devices.setdefault(self.label_guid(device.attributes).lower(), {})
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
            self.cancel_capture()
            self.future.append(self.snapshot())
            description = self.history_labels.pop()
            self.future_labels.append(description)
            self.profile = Profile.from_text(zlib.decompress(self.history.pop()).decode('utf-8'))
            self.sync_profile()
            self.status.set('Undid: ' + description)

    def redo(self):
        if self.profile and self.future:
            self.cancel_capture()
            self.history.append(self.snapshot())
            description = self.future_labels.pop()
            self.history_labels.append(description)
            self.profile = Profile.from_text(zlib.decompress(self.future.pop()).decode('utf-8'))
            self.sync_profile()
            self.status.set('Redid: ' + description)

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
        view = self.view_category.get()
        browse_category = CATEGORIES.get(view, category)
        query = self.search_var.get().casefold().split()
        bound = self.profile.actions() if self.profile else {}
        self.conflict_map = binding_conflicts(self.profile) if self.profile else {}
        conflicts = set(self.conflict_map)
        rows = []
        hidden_count, hidden_categories = 0, set()
        for identity, entry in self.catalogue.actions.items():
            available = category in entry['categories'] or identity in bound
            visible = browse_category in entry['categories'] or (identity in bound and view == 'Current profile')
            if self.context_var.get() != 'All contexts' and entry['context'] != self.context_var.get():
                continue
            group = self.action_group_name(entry)
            if self.action_group.get() != 'All groups' and group != self.action_group.get():
                continue
            haystack = (' '.join([self.action_name(entry), entry['name'], entry['context'], group,
                                  entry.get('description', ''), entry.get('subcategory', '')])).casefold()
            action = bound.get(identity)
            names = [k.get('Information', '') for k in action.findall('./Primary/KEY')] if action is not None else []
            secondary = [k.get('Information', '') for k in action.findall('./Secondary/KEY')] if action is not None else []
            binding = ' + '.join(self.input_display(name) for name in names) + (' / ' + ' + '.join(self.input_display(name) for name in secondary) if secondary else '')
            if query and not all(term in (haystack + ' ' + binding.casefold()) for term in query):
                continue
            if self.bound_only.get() and not binding:
                continue
            if self.unbound_only.get() and binding:
                continue
            if self.conflicts_only.get() and identity not in conflicts:
                continue
            if self.input_filter is not None and action is not None:
                slot_ids = [{str(k.text or '').strip() for k in action.findall(f'./{slot}/KEY')}
                            for slot in ('Primary', 'Secondary')]
                if not any(self.input_filter.issubset(ids) for ids in slot_ids):
                    continue
            elif self.input_filter is not None:
                continue
            if self.input_filter_names is not None:
                if action is None:
                    continue
                family = device_family(self.profile.device.attrib)
                slot_names = [{input_identity(k.get('Information', ''), family) for k in action.findall(f'./{slot}/KEY')}
                              for slot in ('Primary', 'Secondary')]
                def matches(group, names):
                    if group.intersection(names):
                        return True
                    if family == 'keyboard':
                        modifier_bits = {162: 16, 163: 16, 160: 32, 161: 32, 164: 64, 165: 64}
                        return any(pair and modifier_bits.get(pair[1], 0) & int(action.get('Flag', '0'))
                                   for pair in (self.catalogue.resolve(name, family) for name in group))
                    return False
                if not any(all(matches(group, names) for group in self.input_filter_names) for names in slot_names):
                    continue
            if not visible and view != 'All controls' and not self.show_all.get():
                hidden_count += 1
                hidden_categories.update(entry['categories'])
                continue
            rows.append((identity, self.action_name(entry), entry['context'], binding, available))
        index = {'name': 1, 'action': 1, 'context': 2, 'binding': 3}.get(self.sort_column, 1)
        rows.sort(key=lambda r: (r[index].casefold(), r[0]), reverse=self.sort_reverse)
        self.tree.delete(*self.tree.get_children())
        self.row_ids = {}
        for number, (identity, title, context, binding, available) in enumerate(rows):
            row_id = str(number)
            self.row_ids[row_id] = identity
            self.tree.insert('', 'end', iid=row_id, values=(title, context, binding or '—'),
                             tags=('unavailable',) if not available else ('conflict',) if identity in conflicts else ('bound',) if binding else ())
            if self.selected == identity:
                self.tree.selection_set(row_id)
        selected_row = next((row for row, identity in self.row_ids.items() if identity == self.selected), None)
        if selected_row is not None:
            self.tree.focus(selected_row)
            self.tree.see(selected_row)
            self.schedule_reveal()
        elif self.selected:
            if not self.follow_input.get():
                self.cancel_capture()
            self.selected, self.programmatic_selection = None, None
            self.action_title.configure(text='Select a control')
            self.action_id.configure(text='Select a visible row to edit its bindings.')
            self.conflict_detail.set('')
            for slot in self.slot_vars:
                self.slot_keys[slot] = []
                self.slot_vars[slot].set('Unbound')
                self.input_vars[slot].set('')
            self.update_binding_buttons()
        self.count_label.configure(text=f'{len(rows):,} controls · {sum(bool(r[3]) for r in rows):,} bound · {len(conflicts)} possible conflicts · Ctrl/Shift selects several')
        self.group_combo.configure(values=['All groups'] + sorted({self.action_group_name(e) for e in self.catalogue.actions.values()}))
        self.empty_results.place_forget()
        self.show_other_profiles_button.pack_forget()
        if not rows:
            if hidden_count:
                types = ' / '.join(label.replace(' controls', '') for label, value in CATEGORIES.items() if value in hidden_categories)
                self.empty_results_title.configure(text='Controls hidden by profile type')
                self.empty_results_detail.configure(text=f'{hidden_count:,} matching controls belong to {types or "other"} profiles. '
                                                   'Show them below, then select a control to choose a compatible profile. Your current bindings will be kept.')
                self.show_other_profiles_button.pack(anchor='w', pady=(0, 8), before=self.clear_filters_button)
            else:
                self.empty_results_title.configure(text='No controls match these filters')
                self.empty_results_detail.configure(text='Try another search, group or context, or clear the filters. '
                                                   'Bound only, Unbound, Conflicts and input searches can also hide controls.')
            self.empty_results.place(relx=.5, rely=.45, anchor='center', relwidth=.92)

    def show_matching_controls(self):
        self.view_category.set('All controls')
        self.refresh_list()

    @staticmethod
    def action_group_name(entry):
        if entry.get('group'):
            if entry['group'].strip().casefold() in ('camera', 'cameras', 'camera / views'):
                return 'Camera / views'
            return entry['group']
        name = entry['name']
        # App browsing groups; imported ActionDB categories take precedence.
        groups = [('Camera / views', ('CAMERA', 'VIEW', 'DRONE', 'HEADLOOK')),
                  ('Autopilot', ('AP_', 'AUTOPILOT', 'YAW_DAMPER', 'AUTO_THROTTLE')),
                  ('Engine / throttle', ('THROTTLE', 'ENGINE', 'STARTER', 'MIXTURE', 'PROPELLER', 'MAGNETO', 'TURBINE')),
                  ('Fuel', ('FUEL', 'CROSSFEED')),
                  ('Landing gear / brakes', ('GEAR', 'BRAKE', 'STEERING', 'PARKING')),
                  ('Electrical / lights', ('LIGHT', 'BATTERY', 'ALTERNATOR', 'ELECTRICAL', 'AVIONICS')),
                  ('Radio / navigation', ('RADIO', 'COM_', 'NAV', 'ADF', 'DME', 'VOR', 'TRANSPONDER', 'GPS')),
                  ('Flight controls', ('AILERON', 'ELEVATOR', 'RUDDER', 'FLAP', 'TRIM', 'SPOILER', 'CYCLIC', 'COLLECTIVE', 'ROTOR')),
                  ('Simulator / interface', ('MENU', 'PAUSE', 'ATC', 'EFB', 'ASSIST', 'CHECKLIST', 'MAP', 'DEBUG'))]
        return next((group for group, words in groups if any(word in name for word in words)), 'Other controls')

    @staticmethod
    def action_name(entry):
        return entry.get('display_name') or display_name(entry['name'])

    def clear_browse_filters(self):
        self.search_var.set('')
        self.context_var.set('All contexts')
        self.action_group.set('All groups')
        self.view_category.set('Current profile')
        self.bound_only.set(False)
        self.unbound_only.set(False)
        self.conflicts_only.set(False)
        self.input_filter = None
        self.input_filter_names = None

    def select_action(self, _=None):
        selection = self.tree.selection()
        self.record_button.configure(text=f'Record selected ({len(selection)})' if len(selection) > 1 else 'Record selected')
        focus = self.tree.focus() if self.tree.focus() in selection else selection[0] if selection else ''
        if focus in self.row_ids:
            identity = self.row_ids[focus]
            if identity == self.programmatic_selection:
                self.programmatic_selection = None
                return
            if identity == self.selected:
                return
            if not self.follow_input.get():
                self.cancel_capture()
            self.selected = identity
            self.show_action()

    def show_action(self):
        if not self.selected:
            self.update_binding_buttons()
            return
        context, name = self.selected
        self.action_title.configure(text=self.action_name(self.catalogue.actions[self.selected]))
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
            bound_name = self.slot_keys[slot][0][0] if self.slot_keys[slot] else ''
            family = device_family(self.profile.device.attrib) if self.profile else 'joystick'
            rendered = next((label for label, raw in self.input_choice_names.items() if input_identity(raw, family) == input_identity(bound_name, family)), '')
            self.input_vars[slot].set(rendered)
        overlaps = binding_conflicts(self.profile).get(self.selected, []) if self.profile else []
        self.conflict_detail.set(('Possible overlaps in ' + context + ':\n' + '\n'.join(
            f'{own}: {kind} with {self.action_name(self.catalogue.actions[other])} ({other_slot})'
            for other, own, other_slot, kind in overlaps[:5]) + '\nThese may be intentional. Review the other control before changing a binding.') if overlaps else '')
        self.load_axis()
        self.update_binding_buttons()

    def update_binding_buttons(self):
        allowed = bool(self.profile and self.selected and (self.profile.category in self.catalogue.actions[self.selected]['categories'] or self.profile.action(*self.selected) is not None))
        matching_device = self.controller_matches()
        self.profile_hint.pack_forget()
        if self.selected and not allowed:
            chosen = self.selected_profile_type()
            if chosen:
                label = next(label for label, value in CATEGORIES.items() if value == chosen)
                current = self.type_var.get() if self.profile else 'No profile'
                available = ' or '.join(label.replace(' controls', '') for label, value in CATEGORIES.items()
                                        if value in self.catalogue.actions[self.selected]['categories'])
                self.profile_hint_text.configure(text=f'{current} cannot bind this control. This control uses {available} profiles.')
                blank = self.profile and self.profile.can_change_category()
                self.profile_hint_button.configure(text=('Use ' if blank else 'New ') + label.replace(' controls', '') + ' profile')
                self.profile_hint_button.pack(anchor='w', pady=(6, 0))
                self.profile_hint.pack(before=self.tabs, fill='x')
        elif allowed and not matching_device:
            self.profile_hint_text.configure(text='Recording is unavailable because the selected controller does not match this profile. Select its controller, or click Use for this profile. Verified inputs can also be chosen below.')
            self.profile_hint_button.pack_forget()
            self.profile_hint.pack(before=self.tabs, fill='x')
        for slot, label, button in self.binding_buttons:
            enabled = allowed and (label != 'Get Input' or matching_device) and (label != 'Clear' or bool(self.slot_keys[slot]))
            button.configure(state='normal' if enabled else 'disabled')
        self.record_button.configure(state='normal' if allowed and matching_device else 'disabled')

    def editable(self):
        if not self.profile or not self.selected:
            self.error('Create or open a profile, then select a control.')
            return False
        entry = self.catalogue.actions[self.selected]
        if self.profile.category not in entry['categories'] and self.selected not in self.profile.actions():
            self.error('This control is not available in this profile type. Choose the matching General / Airplane / Helicopter profile.')
            return False
        return True

    def bind(self, slot, pairs, add=False, modifiers=None):
        if not self.editable():
            return
        self.checkpoint(f'{slot} binding · {display_name(self.selected[1])}')
        if add:
            pairs = self.slot_keys[slot] + [p for p in pairs if p not in self.slot_keys[slot]]
        entry = self.catalogue.actions[self.selected]
        self.profile.set_binding(*self.selected, slot, pairs, defaults=entry['attributes'])
        # Let a full-range Windows analog input determine the basic input type;
        # retain modifiers and keep split +/− inputs available for digital actions.
        action = self.profile.action(*self.selected)
        live_axes = {normalized(o.msfs_name()) for o in self.controller.objects if o.kind == 'axis'} if self.controller_matches() else set()
        if pairs and any(('axis' in information.casefold() or 'slider' in information.casefold() or normalized(information) in live_axes)
                         and not information.rstrip().endswith(('+', '-')) for information, _ in pairs):
            action.set('Flag', str((int(action.get('Flag', '2')) & ~7) | 4))
            live = next((obj for obj in self.controller.objects if obj.kind == 'axis' and any(normalized(name) == normalized(obj.msfs_name()) for name, _ in pairs)), None) if self.controller_matches() else None
            if live and live.axis in self.profile.axis_names():
                self.axis_var.set(live.axis)
        if device_family(self.profile.device.attrib) == 'keyboard':
            ids = {int(value) for _, value in pairs}
            modifiers = (modifiers or 0) | (16 if ids.intersection({162, 163}) else 0) | (32 if ids.intersection({160, 161}) else 0) | (64 if ids.intersection({164, 165}) else 0)
        if modifiers is not None:
            flag = (int(action.get('Flag', '2')) & ~(16 | 32 | 64)) | modifiers
            action.set('Flag', str(flag & ~8 if modifiers else flag))
        self.show_action()
        self.refresh_list()
        self.status.set(f'{slot} binding updated. Export XML when ready.')

    def manual_binding(self, slot, add=False):
        self.cancel_capture()
        name = self.input_choice_names.get(self.input_vars[slot].get(), self.input_vars[slot].get())
        pair = self.resolve_input(name)
        if not pair:
            self.error('This input has no verified MSFS numeric ID. Open a real MSFS export containing it to learn the ID, then try again.')
            return
        self.bind(slot, [pair], add)

    def clear_binding(self, slot):
        self.cancel_capture()
        self.bind(slot, [])

    def clear_selected(self):
        targets = [self.row_ids[row] for row in self.tree.selection()]
        if not self.profile or not targets:
            self.error('Select controls to clear. Ctrl/Shift selects several.')
            return
        slot = self.record_slot.get()
        self.cancel_capture()
        self.checkpoint(f'Clear {slot.lower()} bindings · {len(targets)} controls')
        for target in targets:
            if self.profile.action(*target) is not None:
                self.profile.set_binding(*target, slot, [])
        self.refresh_list()
        self.show_action()
        self.feedback('BINDINGS CLEARED · NOT RECORDING', f'Cleared {slot.lower()} bindings on {len(targets)} selected controls. Undo restores them.', 'success')

    def selected_actions_menu(self, event=None):
        if event:
            row = self.tree.identify_row(event.y)
            if row and row not in self.tree.selection():
                self.tree.selection_set(row)
                self.tree.focus(row)
        menu = tk.Menu(self.root, tearoff=False)
        state = 'normal' if self.tree.selection() else 'disabled'
        menu.add_command(label='Clear selected ' + self.record_slot.get().lower() + ' bindings', command=self.clear_selected, state=state)
        menu.add_command(label='Apply behavior to selected controls…', command=self.batch_behavior, state=state)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def batch_behavior(self):
        targets = [self.row_ids[row] for row in self.tree.selection()]
        if not self.profile or not targets:
            self.error('Select controls before applying behavior to several actions.')
            return
        if any(self.profile.category not in self.catalogue.actions[t]['categories'] and t not in self.profile.actions() for t in targets):
            self.error('Select controls available in the current profile type.')
            return
        window = tk.Toplevel(self.root)
        window.title('Batch behavior')
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=f'Apply behavior to {len(targets)} selected controls', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Choose which fields to replace. Bindings and other fields are kept. Undo restores the whole batch.', wraplength=460).pack(anchor='w', pady=10)
        fields = {}
        for name, initial in [('Flag', self.flag_value.get()), ('ValueEvent', self.event_value.get()), ('Delay', self.delay_value.get())]:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=5)
            enabled, value = tk.BooleanVar(value=name == 'Flag'), tk.StringVar(value=initial)
            ttk.Checkbutton(row, text=name, variable=enabled, width=20).pack(side='left')
            ttk.Entry(row, textvariable=value, width=15).pack(side='left')
            fields[name] = (enabled, value)
        def apply():
            changes = {name: var.get() for name, (enabled, var) in fields.items() if enabled.get()}
            candidate = Profile.from_text(self.profile.to_text())
            try:
                for target in targets:
                    candidate.action(*target, create=True, defaults=self.catalogue.actions[target]['attributes']).attrib.update(changes)
                if candidate.validate():
                    raise ValueError('\n'.join(candidate.validate()[:6]))
                self.checkpoint(f'Batch behavior · {len(targets)} controls')
                self.profile = candidate
                self.refresh_list()
                self.show_action()
                self.feedback('BEHAVIOR SAVED · NOT RECORDING', f'Updated {len(targets)} controls. Undo reverses the batch.', 'success')
                window.destroy()
            except ValueError as exc:
                messagebox.showerror('Batch behavior', str(exc), parent=window)
        ttk.Button(frame, text='Apply to selected controls', command=apply, style='Accent.TButton').pack(fill='x', pady=12)

    def reset_axis(self):
        for name, value in AXIS_DEFAULTS.items():
            self.axis_values[name].set(value)
        self.apply_axis()

    def guided_setup(self):
        if not self.profile or not self.controller:
            self.setup_walkthrough()
            return
        recommended = {
            'AIRPLANE': ('KEY_AXIS_AILERONS_SET', 'KEY_AXIS_ELEVATOR_SET', 'KEY_AXIS_RUDDER_SET',
                         'KEY_AXIS_THROTTLE_SET', 'KEY_GEAR_TOGGLE', 'KEY_PARKING_BRAKES',
                         'KEY_FLAPS_INCR', 'KEY_FLAPS_DECR', 'KEY_ELEV_TRIM_UP', 'KEY_ELEV_TRIM_DN'),
            'HELICOPTER': ('KEY_AXIS_CYCLIC_LATERAL_SET', 'KEY_AXIS_CYCLIC_LONGITUDINAL_SET',
                           'KEY_AXIS_COLLECTIVE_SET', 'KEY_AXIS_TAIL_ROTOR_SET', 'KEY_ROTOR_BRAKE', 'KEY_PARKING_BRAKES'),
            'GENERAL': ('KEY_COCKPIT_FREELOOK_HRZ_SET', 'KEY_COCKPIT_FREELOOK_VRTC_SET',
                        'KEY_COCKPIT_QUICKVIEW_RESET', 'KEY_PAUSE_TOGGLE')}
        targets = []
        for name in recommended.get(self.profile.category, ()):
            match = next((key for key, entry in self.catalogue.actions.items()
                          if key[1] == name and self.profile.category in entry['categories']), None)
            if match:
                targets.append(match)
        window = tk.Toplevel(self.root)
        window.title('Guided controller setup')
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Pick the controls you want to set up', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='You will record one input at a time. Use Skip for inputs this controller does not have. Existing bindings on chosen actions will be replaced; Undo restores them.', wraplength=500).pack(anchor='w', pady=10)
        picks = []
        for target in targets:
            selected = tk.BooleanVar(value=True)
            ttk.Checkbutton(frame, text=self.action_name(self.catalogue.actions[target]), variable=selected).pack(anchor='w', pady=3)
            picks.append((target, selected))
        def start():
            chosen = [target for target, selected in picks if selected.get()]
            if not chosen:
                return
            self.cancel_capture()
            self.clear_browse_filters()
            self.refresh_list()
            self.selected = chosen[0]
            self.programmatic_selection = self.selected
            self.tree.selection_set([row for row, target in self.row_ids.items() if target in chosen])
            # Keep the instructional order rather than alphabetical table order.
            self.recording = {'targets': chosen, 'index': 0, 'slot': self.record_slot.get(), 'recorded': 0,
                              'skipped': 0, 'waiting': False, 'stable_since': None, 'last': dict(self.current_values)}
            window.destroy()
            self.record_next()
        ttk.Label(frame, text='Binding slot').pack(anchor='w', pady=(8, 0))
        ttk.Combobox(frame, textvariable=self.record_slot, values=['Primary', 'Secondary'], state='readonly').pack(fill='x', pady=4)
        ttk.Button(frame, text='Start guided recording', command=start, style='Accent.TButton').pack(fill='x', pady=(12, 0))

    def tools_menu(self):
        menu = tk.Menu(self.root, tearoff=False)
        for title, command in [('Setup walkthrough', self.setup_walkthrough),
                                ('Resume local working copy', self.draft_browser),
                                ('Device Keys / input ID reference', self.device_keys),
                                ('Saved MSFS profiles (open a copy)', self.saved_profile_browser),
                                ('Import control definitions / reference profiles', self.import_definitions),
                                ('Profile / device metadata', self.edit_metadata),
                                ('Undo history', self.undo_history),
                                ('DeviceConfig source editor', lambda: self.sdk_editor('DeviceConfig')),
                                ('ActionDB source editor', lambda: self.sdk_editor('ActionDefinition')),
                                ('RemapDB source editor', lambda: self.sdk_editor('RemapActions')),
                                ('Export SDK DefaultInput source', self.export_sdk)]:
            menu.add_command(label=title, command=command)
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def scan_saved_profiles(self, quiet=False):
        if self.profile_scan_running:
            return
        self.profile_scan_running = True
        self.profile_scan_progress.set('Loading saved profiles… You can keep using the editor or close this browser.')
        self.profile_scan_cancel = threading.Event()
        from .local_profiles import scan_profiles
        def work():
            try:
                self.profile_scan_results.put((scan_profiles(cancel_event=self.profile_scan_cancel), None))
            except Exception as exc:
                self.profile_scan_results.put((None, str(exc)))
        threading.Thread(target=work, name='MSFS profile scan', daemon=True).start()
        self.root.after(50, lambda: self.poll_profile_scan(quiet))

    def refresh_saved_browser(self):
        if self.saved_browser_window is not None and self.saved_browser_window.winfo_exists() and self.saved_browser_refresh:
            self.saved_browser_refresh()

    def poll_profile_scan(self, quiet):
        try:
            rows, error = self.profile_scan_results.get_nowait()
        except queue.Empty:
            self.root.after(50, lambda: self.poll_profile_scan(quiet))
            return
        if error:
            self.profile_scan_running = False
            self.profile_scan_progress.set('Could not load saved profiles: ' + error + '. Try Refresh, or use Open XML.')
            self.refresh_saved_browser()
            return
        self.saved_profiles = rows
        self.profile_scan_loaded = True
        self.profile_scan_progress.set(f'{len(rows)} profiles found. Loading their control references…')
        self.refresh_saved_browser()
        self.merge_saved_references(rows, 0, len(self.catalogue.key_pairs), quiet)

    def merge_saved_references(self, rows, index, before, quiet):
        started = time.perf_counter()
        try:
            while index < len(rows) and time.perf_counter() - started < .02:
                self.catalogue.learn(rows[index]['profile'])
                index += 1
        except Exception as exc:
            self.profile_scan_running = False
            self.profile_scan_progress.set(f'Profiles loaded; could not learn their references: {exc}. Try Refresh or Open XML.')
            self.refresh_saved_browser()
            return
        if index < len(rows):
            self.profile_scan_progress.set(f'{len(rows)} profiles found. Loading control references… {index}/{len(rows)}')
            self.root.after(10, lambda: self.merge_saved_references(rows, index, before, quiet))
            return
        try:
            self.catalogue.save_library()
            self.context_combo.configure(values=['All contexts'] + sorted({a[0] for a in self.catalogue.actions}))
            self.update_input_choices()
            self.refresh_list()
            self.add_saved_system_devices()
            self.profile_scan_progress.set(f'{len(rows)} profiles found. Open a copy to edit it offline.' if rows else
                                           'No local Store profile XML was found. Use Open XML with a profile exported by MSFS.')
            if not quiet and not (self.capture or self.recording or self.follow_input.get()):
                self.feedback('SAVED PROFILES FOUND · NOT RECORDING', f'Found {len(rows)} local MSFS profiles and learned {len(self.catalogue.key_pairs) - before} additional input references.', 'success')
        except Exception as exc:
            self.profile_scan_progress.set(f'Profiles loaded; could not finish learning their references: {exc}. You can still open a copy.')
        finally:
            self.profile_scan_running = False
            self.refresh_saved_browser()

    def add_saved_system_devices(self):
        # Discover built-in devices without closing/reopening the active reader.
        previous = self.selected_device()
        fresh = system_devices([row['profile'] for row in self.saved_profiles], self.catalogue)
        if isinstance(previous, SystemDevice):
            for index, device in enumerate(fresh):
                if device.family == previous.family and device.slot == previous.slot:
                    fresh[index] = previous
        self.devices = [device for device in self.devices if not isinstance(device, SystemDevice)] + fresh
        self.device_combo.configure(values=[device.name if isinstance(device, SystemDevice) else f'{device.name}  [{device.instance_guid[1:9]}]' for device in self.devices])
        if previous in self.devices:
            self.device_combo.current(self.devices.index(previous))
        elif not self.controller and self.devices:
            self.device_combo.current(0)
            self.select_device()
        if self.controller:
            family = device_family(self.controller.device.attributes)
            for obj in self.controller.objects:
                pair = self.catalogue.resolve(obj.msfs_name('Up') if obj.kind == 'pov' else obj.msfs_name(), family)
                self.monitor.set(str(obj.offset), 'support', str(pair[1]) if pair else 'Needs reference')

    def saved_profile_browser(self):
        if self.saved_browser_window is not None and self.saved_browser_window.winfo_exists():
            self.saved_browser_window.lift()
            return self.saved_browser_window
        self.cancel_capture()
        window = tk.Toplevel(self.root)
        self.saved_browser_window = window
        window.title('Saved MSFS profiles · open a copy')
        window.geometry('870x570')
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Start from your existing simulator profiles', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Open a copy, make changes, then Export XML and import it in MSFS. This browser reads local Store saves; it does not write to cloud storage.', wraplength=800).pack(anchor='w', pady=10)
        search = tk.StringVar()
        search_row = ttk.Frame(frame)
        search_row.pack(fill='x', pady=(0, 8))
        ttk.Entry(search_row, textvariable=search).pack(side='left', fill='x', expand=True)
        refresh_button = ttk.Button(search_row, text='Refresh', command=lambda: (self.scan_saved_profiles(quiet=True), refresh()))
        refresh_button.pack(side='right', padx=(8, 0))
        table = ttk.Frame(frame)
        table.pack(fill='both', expand=True)
        listing = ttk.Treeview(table, columns=('name', 'device', 'type', 'bindings'), show='headings', selectmode='browse')
        for key, title, width in [('name', 'Profile', 260), ('device', 'Device', 260), ('type', 'Type', 120), ('bindings', 'Bound', 70)]:
            listing.heading(key, text=title)
            listing.column(key, width=width)
        scroll = ttk.Scrollbar(table, orient='vertical', command=listing.yview)
        listing.configure(yscrollcommand=scroll.set)
        listing.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        displayed_rows = {}
        def refresh(*_):
            selected = listing.selection()
            previous_path = displayed_rows.get(selected[0], {}).get('path') if selected else None
            listing.delete(*listing.get_children())
            displayed_rows.clear()
            for index, row in enumerate(self.saved_profiles):
                if all(term in f'{row["name"]} {row["device"]} {row["category"]}'.casefold() for term in search.get().casefold().split()):
                    bound = row.get('bindings')
                    if bound is None:
                        bound = row['bindings'] = row['profile'].bound_slot_count()
                    displayed_rows[str(index)] = row
                    listing.insert('', 'end', iid=str(index), values=(row['name'], row['device'], row['category'], bound))
                    if row.get('path') == previous_path:
                        listing.selection_set(str(index))
            children = listing.get_children()
            if children and not listing.selection():
                listing.selection_set(children[0])
            open_button.configure(state='normal' if children else 'disabled')
            refresh_button.configure(state='disabled' if self.profile_scan_running else 'normal')
            progress.stop()
            if self.profile_scan_running:
                progress.pack(fill='x', pady=(8, 0), before=progress_label)
                progress.start(20)
            else:
                progress.pack_forget()
        def open_copy(*_):
            selected = listing.selection()
            if not selected:
                return
            row = displayed_rows[selected[0]]
            # An export prompt pumps Tk events; a scan can replace/reorder the list.
            if not self.can_discard():
                return
            self.catalogue.learn(row['profile'])
            self.catalogue.save_library()
            self.profile = Profile.from_text(row['profile'].to_text())
            self.draft_session, self.last_draft = str(uuid.uuid4()), None
            self.path = None
            self.saved_text = self.profile.to_text()
            self.history, self.future, self.history_labels, self.future_labels = [], [], [], []
            self.selected = None
            self.clear_browse_filters()
            self.sync_profile()
            self.update_input_choices()
            self.select_profile_controller()
            self.feedback('PROFILE COPY OPENED · NOT RECORDING', f'{row["name"]} · {row["device"]}. Changes stay in this app until you export and import the XML.', 'success')
            window.destroy()
        search.trace_add('write', refresh)
        listing.bind('<Double-1>', open_copy)
        progress = ttk.Progressbar(frame, mode='indeterminate')
        progress_label = ttk.Label(frame, textvariable=self.profile_scan_progress, style='Muted.TLabel', wraplength=800)
        progress_label.pack(anchor='w', pady=10)
        open_button = ttk.Button(frame, text='Open selected copy', command=open_copy, style='Accent.TButton')
        open_button.pack(fill='x')
        self.saved_browser_refresh = refresh
        if not self.profile_scan_loaded:
            self.scan_saved_profiles(quiet=True)
        refresh()
        return window

    def setup_walkthrough(self):
        window = tk.Toplevel(self.root)
        window.title('Set up a controller')
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='From plugged in to ready to import', style='Heading.TLabel').pack(anchor='w')
        steps = [('1 · Connect and test', 'Select your controller and click Test controller. Every reported button and axis should react.'),
                 ('2 · Give inputs useful names', 'Click a numbered button or axis scale, enter a name, then Set name. Names stay with this controller.'),
                 ('3 · Choose a profile', 'Click New and choose General, Airplane or Helicopter. Saved profiles opens a copy of an existing preset; Open XML reads an exported file.'),
                 ('4 · Find and record', 'Use Show, context and text filters. Get Input records one binding. Ctrl/Shift selects a group for Record selected.'),
                 ('5 · Review', 'Use Follow controller to press an input and jump to its assignments. Review Behavior, Axis tuning and Conflicts.'),
                 ('6 · Export and import', 'Export XML. In MSFS Settings → Controls, select the same controller and matching profile type, then its cogwheel → Import.')]
        for title, body in steps:
            ttk.Label(frame, text=title, style='Heading.TLabel').pack(anchor='w', pady=(12, 3))
            ttk.Label(frame, text=body, wraplength=530).pack(anchor='w')
        ttk.Button(frame, text='Open controller test', command=lambda: (self.controller_test_window(), window.destroy())).pack(fill='x', pady=(18, 0))

    def device_keys(self):
        window = tk.Toplevel(self.root)
        window.title('Device Keys · verified input IDs')
        window.geometry('720x540')
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Known MSFS input names and numeric IDs', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Verified from reference profiles and your imports. Unknown IDs are learned by importing a real simulator export.', wraplength=670).pack(anchor='w', pady=8)
        query = tk.StringVar()
        family = tk.StringVar(value=device_family(self.profile.device.attrib) if self.profile else 'joystick')
        ttk.Combobox(frame, textvariable=family, state='readonly', values=['joystick', 'keyboard', 'mouse', 'gamepad']).pack(fill='x', pady=6)
        ttk.Entry(frame, textvariable=query).pack(fill='x', pady=6)
        tree = ttk.Treeview(frame, columns=('name', 'id', 'state'), show='headings')
        for name, title, width in [('name', 'Input name', 350), ('id', 'Numeric ID', 90), ('state', 'Reference', 160)]:
            tree.heading(name, text=title)
            tree.column(name, width=width)
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        def refresh(*_):
            tree.delete(*tree.get_children())
            for name, value in sorted(self.catalogue.keys_for(family.get()).items()):
                if query.get().casefold() in f'{name} {value}'.casefold():
                    tree.insert('', 'end', values=(name, value, 'Verified' if self.catalogue.resolve(name, family.get()) else 'Conflicting references'))
        query.trace_add('write', refresh)
        family.trace_add('write', refresh)
        refresh()

    def import_definitions(self):
        from .sdk import SDKDocument
        paths = filedialog.askopenfilenames(title='Learn controls and input IDs from real references',
                   filetypes=[('Profiles / ActionDB', '*.xml *.actiondb'), ('All files', '*.*')])
        count, failures = 0, []
        for path in paths:
            try:
                if 'ActionDefinition' in Path(path).read_text(encoding='utf-8-sig')[:1000]:
                    count += self.catalogue.learn_actiondb(SDKDocument.load(path), self.profile.category if self.profile else CATEGORIES[self.type_var.get()])
                else:
                    profile = Profile.load(path)
                    self.catalogue.learn(profile)
                    count += len(profile.actions())
            except (OSError, ValueError) as exc:
                failures.append(Path(path).name + ': ' + str(exc))
        if paths:
            self.catalogue.save_library()
            self.context_combo.configure(values=['All contexts'] + sorted({a[0] for a in self.catalogue.actions}))
            self.update_input_choices()
            self.refresh_list()
            self.feedback('REFERENCE IMPORT FINISHED · NOT RECORDING', f'Learned {count:,} action entries from {len(paths) - len(failures)} files.' + (' Skipped: ' + '; '.join(failures[:3]) if failures else ''), 'error' if failures else 'success')

    def import_action_document(self, document):
        category = self.profile.category if self.profile else CATEGORIES[self.type_var.get()]
        count = self.catalogue.learn_actiondb(document, category)
        self.catalogue.save_library()
        self.context_combo.configure(values=['All contexts'] + sorted({a[0] for a in self.catalogue.actions}))
        self.refresh_list()
        self.feedback('CONTROLS ADDED · NOT RECORDING', f'Imported {count} controls into the library for {category}. Search their English names, categories or event IDs.', 'success')

    def sdk_editor(self, kind):
        from .sdk import SDKDocument
        from .sdk_editor import SDKEditor
        device = self.selected_device()
        document = SDKDocument.device_config(device, self.labels, self.catalogue) if kind == 'DeviceConfig' and device else SDKDocument.new(kind)
        editor = SDKEditor(self, document)
        self.sdk_editors.append(editor)

    def undo_history(self):
        if not self.profile:
            self.error('Create or open a profile before viewing its history.')
            return
        window = tk.Toplevel(self.root)
        window.title('Undo history')
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Restore any state in this editing session', style='Heading.TLabel').pack(anchor='w', pady=(0, 10))
        listing = tk.Listbox(frame, width=68, height=18, exportselection=False)
        listing.pack(fill='both', expand=True)
        position = len(self.history)
        labels = ['Opened / new profile'] + self.history_labels + list(reversed(self.future_labels))
        for index, name in enumerate(labels):
            listing.insert('end', f'{index}: {name}' + ('  ← current' if index == position else ''))
        listing.selection_set(position)
        listing.see(position)
        def restore():
            if listing.curselection():
                target = listing.curselection()[0]
                self.cancel_capture()
                for _ in range(abs(target - position)):
                    self.undo() if target < position else self.redo()
                window.destroy()
        ttk.Button(frame, text='Restore selected state', command=restore).pack(fill='x', pady=(10, 0))

    def edit_metadata(self):
        if not self.profile:
            self.error('Open or create a profile before editing its device metadata.')
            return
        window = tk.Toplevel(self.root)
        window.title('Profile and device metadata')
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Device identity and existing profile metadata', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Match these to a real device or aircraft export. Composite ID and hardware version distinguish parts of a controller.', wraplength=600).pack(anchor='w', pady=10)
        fields = []
        nodes = [('Device', self.profile.device), ('Aircraft info', self.profile.device.find('AircraftInfo')),
                 ('Profile', self.profile.container if self.profile.format == 'sdk' else self.profile.container.find('FriendlyName'))]
        for title, node in nodes:
            if node is None:
                continue
            ttk.Label(frame, text=title, style='Heading.TLabel').pack(anchor='w', pady=(8, 3))
            for name, value in node.attrib.items():
                row = ttk.Frame(frame)
                row.pack(fill='x', pady=3)
                ttk.Label(row, text=name, width=24).pack(side='left')
                var = tk.StringVar(value=value)
                ttk.Entry(row, textvariable=var, width=40).pack(side='left', fill='x', expand=True)
                fields.append((title, name, var))
        def apply():
            candidate = Profile.from_text(self.profile.to_text())
            targets = {'Device': candidate.device, 'Aircraft info': candidate.device.find('AircraftInfo'),
                       'Profile': candidate.container if candidate.format == 'sdk' else candidate.container.find('FriendlyName')}
            for title, name, var in fields:
                targets[title].set(name, var.get())
            errors = candidate.validate()
            if errors:
                messagebox.showerror('Profile metadata', '\n'.join(errors[:6]), parent=window)
                return
            self.checkpoint('Edit profile / device metadata')
            self.profile = candidate
            self.catalogue.learn(candidate)
            self.sync_profile()
            self.update_input_choices()
            self.feedback('METADATA SAVED · NOT RECORDING', 'Profile metadata updated. Export XML saves these changes.', 'success')
            window.destroy()
        ttk.Button(frame, text='Apply metadata', command=apply, style='Accent.TButton').pack(fill='x', pady=(15, 0))

    def export_sdk(self):
        import xml.etree.ElementTree as ET
        if not self.profile:
            self.error('Create or open a profile before exporting SDK source.')
            return
        root = ET.Element('ProfileDocument')
        node = ET.SubElement(root, 'DefaultInput', Primary='0', PlatformAvailability='PC')
        ET.SubElement(node, 'Version', Num='0')
        device = deepcopy(self.profile.device)
        # Aircraft-category placement is part of the SDK project, not this element.
        for info in device.findall('AircraftInfo'):
            device.remove(info)
        node.append(device)
        result = Profile(root, 'sdk')
        path = filedialog.asksaveasfilename(title='Export DefaultInput package source (requires SDK build)', defaultextension='.xml', initialfile='controller.xml')
        if path:
            try:
                result.save(path)
                self.feedback('SDK SOURCE EXPORTED · NOT RECORDING', 'Saved DefaultInput XML. Add it to an SDK input project and build/test that package in MSFS.', 'success')
            except (OSError, ValueError) as exc:
                self.error(exc)

    def start_capture(self, slot, guided=False):
        if self.recording and not guided:
            self.stop_recording()
        if not self.editable():
            return
        if not self.controller:
            self.error('Connect a controller and click Refresh before using Get Input.')
            return
        if not self.controller_matches():
            self.error('The live controller differs from this profile. Choose Use for this profile before capturing inputs.')
            return
        try:
            self.last_capture_slot = slot
            self.last_capture_search = False
            self.capture_result = ''
            if hasattr(self.controller, 'reset_baseline'):
                self.controller.reset_baseline()
            baseline = self.controller.read()
            self.capture = {'slot': slot, 'baseline': dict(baseline), 'deadline': time.monotonic() + 12,
                            'names': [], 'settle': None, 'modifiers': 0}
            self.follow_input.set(False)
            self.follow_pending = None
            self.status.set(f'Listening for {slot.lower()} input… Move an axis or press a button. Escape cancels.')
            if guided:
                self.status.set(f'Recording {self.recording["index"] + 1}/{len(self.recording["targets"])}: {display_name(self.selected[1])}. Move/press an input; Skip advances, Stop ends.')
            self.feedback('RECORDING · LISTENING', self.status.get(), 'listen', detected='')
        except Exception as exc:
            self.error(exc)

    def cancel_capture(self):
        active = bool(self.capture or self.recording or self.follow_input.get())
        self.capture = None
        self.recording = None
        self.follow_input.set(False)
        self.follow_pending = None
        self.capture_result = ''
        if active:
            self.status.set('Recording / input search stopped. Existing bindings are kept.')
        self.feedback('NOT RECORDING', self.status.get() if active else 'Ready. Get Input records one binding; Record selected guides several actions.', detected='')

    def record_selected(self):
        selection = self.tree.selection()
        if not selection or not self.profile:
            self.error('Select one or more actions in the list. Use Ctrl or Shift to select several.')
            return
        if not self.controller_matches():
            self.error('Select the controller used by this profile before recording.')
            return
        targets = [self.row_ids[row] for row in selection]
        category = self.profile.category
        if any(category not in self.catalogue.actions[target]['categories'] and target not in self.profile.actions() for target in targets):
            self.error('Some selected actions belong to another profile type. Select compatible actions before recording.')
            return
        self.cancel_capture()
        self.recording = {'targets': targets, 'index': 0, 'slot': self.record_slot.get(),
                          'recorded': 0, 'skipped': 0, 'waiting': False, 'stable_since': None, 'last': dict(self.current_values)}
        self.record_next()

    def find_input(self):
        if not self.controller or not self.profile:
            self.error('Open a profile and connect its controller to find bindings by input.')
            return
        if not self.controller_matches():
            self.error('Choose the controller used by this profile before searching by input.')
            return
        self.cancel_capture()
        if hasattr(self.controller, 'reset_baseline'):
            self.controller.reset_baseline()
        self.capture = {'slot': None, 'baseline': dict(self.controller.read()), 'deadline': time.monotonic() + 12,
                        'names': [], 'settle': None, 'search': True}
        self.last_capture_search = True
        self.status.set('Find input: press a button, move an axis or turn a hat to show its assigned actions.')
        self.feedback('FIND INPUT · LISTENING', self.status.get(), 'search', detected='')

    def toggle_follow(self):
        enabled = self.follow_input.get()
        self.cancel_capture()
        if not enabled:
            return
        if not self.controller_matches():
            self.error('Connect the controller used by this profile before following its inputs.')
            return
        self.follow_input.set(True)
        self.follow_baseline = dict(self.current_values)
        self.feedback('FOLLOW CONTROLLER · NOT RECORDING', 'Press an input to jump to its bindings. Repeat with another input to search again. Escape stops following.', 'search', detected='')

    def jump_to_inputs(self, pairs):
        self.jump_to_names([pair[0] for pair in pairs])

    def jump_to_names(self, names):
        self.clear_browse_filters()
        self.input_filter_names = []
        family = device_family(self.profile.device.attrib)
        for name in names:
            group = {input_identity(name, family)}
            if 'axis' in name.casefold() or 'slider' in name.casefold():
                base = normalized(name).rstrip('+-')
                group.update((base, base + '+', base + '-'))
            self.input_filter_names.append(group)
        self.refresh_list()
        rows = self.tree.get_children()
        if rows:
            row = rows[0]
            self.selected = self.row_ids[row]
            self.programmatic_selection = self.selected
            self.tree.selection_set(row)
            self.tree.focus(row)
            self.tree.see(row)
            self.show_action()
        else:
            self.selected = None
            self.action_title.configure(text='No matching binding')
            self.action_id.configure(text='This input is not assigned in the current profile. Clear input filter to choose a control.')
            for slot in self.slot_vars:
                self.slot_keys[slot] = []
                self.slot_vars[slot].set('Unbound')
                self.input_vars[slot].set('')
            self.update_binding_buttons()
        names = ' + '.join(self.input_display(name) for name in names)
        count = len(rows)
        self.status.set(f'{count} binding match(es) for {names}.' + (' Selected the first match.' if count else ' This input is not assigned in this profile.'))
        self.feedback('INPUT FOUND · NOT RECORDING' if count else 'UNASSIGNED INPUT · NOT RECORDING',
                      self.status.get() + ' Clear input filter returns to all controls.', 'success' if count else 'search', detected=names)

    def clear_input_filter(self):
        self.input_filter = None
        self.input_filter_names = None
        self.refresh_list()
        self.status.set('Input filter cleared.')
        self.feedback('FOLLOW CONTROLLER · NOT RECORDING' if self.follow_input.get() else 'NOT RECORDING',
                      'Input filter cleared.' + (' Press another input to find its bindings.' if self.follow_input.get() else ' Select a control to continue.'),
                      'search' if self.follow_input.get() else 'idle', detected='')

    def record_next(self):
        if not self.recording:
            return
        session = self.recording
        if session['index'] >= len(session['targets']):
            count = len(session['targets'])
            self.recording = None
            self.capture = None
            self.status.set(f'Recording finished: {session["recorded"]} saved, {session["skipped"]} skipped out of {count}. Review the bindings, then Export XML.')
            self.feedback('FINISHED · NOT RECORDING', self.status.get(), 'success')
            return
        self.selected = session['targets'][session['index']]
        self.programmatic_selection = self.selected
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
            self.recording['skipped'] += 1
            self.record_next()

    def stop_recording(self):
        if self.recording:
            self.cancel_capture()
            self.status.set('Recording stopped. Bindings already recorded are kept; Undo can reverse them.')

    def retry_capture(self):
        if self.recording:
            self.record_next()
        elif self.last_capture_search:
            self.find_input()
        else:
            self.start_capture(self.last_capture_slot)

    def capture_names(self, baseline, current):
        kind = {'Buttons / keys only': 'button', 'Axes only': 'axis', 'Hats only': 'pov'}.get(self.capture_mode.get())
        objects = [obj for obj in self.controller.objects if not kind or obj.kind == kind]
        names = changed_inputs(objects, baseline, current, self.split_axes.get(), self.split_pov.get())
        axes = [obj for obj in objects if obj.kind == 'axis' and abs(current.get(obj.offset, 0) - baseline.get(obj.offset, 0)) >= .18]
        if axes:
            dominant = max(axes, key=lambda obj: abs(current[obj.offset] - baseline[obj.offset]))
            if self.capture:
                offset = self.capture.setdefault('axis_offset', dominant.offset)
                dominant = next((obj for obj in objects if obj.offset == offset), dominant)
            objects = [obj for obj in objects if obj.kind != 'axis' or obj.offset == dominant.offset]
            names = changed_inputs(objects, baseline, current, self.split_axes.get(), self.split_pov.get())
        if self.profile and device_family(self.profile.device.attrib) == 'keyboard' and not self.include_modifiers.get():
            names = [name for name in names if not self.resolve_input(name) or self.resolve_input(name)[1] not in (160, 161, 162, 163, 164, 165)]
        return names

    def flags_changed(self):
        self.flag_value.set(str(sum(bit for bit, var in self.flag_vars.items() if var.get())))

    def apply_behavior(self):
        self.cancel_capture()
        if not self.editable():
            return
        try:
            flag = int(self.flag_value.get())
            value, delay = float(self.event_value.get()), float(self.delay_value.get())
            if not 0 <= flag <= 65535 or not math.isfinite(value) or not math.isfinite(delay) or delay < 0:
                raise ValueError('Flags must be 0–65535. Value and delay must be finite; delay must be nonnegative.')
            self.checkpoint('Behavior · ' + display_name(self.selected[1]))
            action = self.profile.action(*self.selected, create=True, defaults=self.catalogue.actions[self.selected]['attributes'])
            action.attrib.update(Flag=str(flag), ValueEvent=str(value), Delay=str(delay))
            self.show_action()
            self.status.set('Behavior saved. Digital repeats while held; Once on press sends one event. On release triggers on release.')
            self.feedback('BEHAVIOR SAVED · NOT RECORDING', self.status.get(), 'success')
        except ValueError as exc:
            self.error(exc)

    def load_axis(self):
        values = dict(AXIS_DEFAULTS)
        if self.profile:
            names = self.profile.axis_names()
            self.axis_combo.configure(values=names)
            if self.axis_var.get() not in names:
                self.axis_var.set(names[0])
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
        self.cancel_capture()
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
            self.checkpoint(f'Axis {self.axis_var.get()} · {self.axis_scope.get()}')
            self.profile.set_axis(self.axis_var.get(), values, action, slot)
            if action is not None:
                action.set('Flag', str(int(action.get('Flag', '4')) | 4096))
            self.show_action()
            self.status.set(f'{self.axis_var.get()} settings saved to {self.axis_scope.get().lower()}.')
            self.feedback('AXIS SETTINGS SAVED · NOT RECORDING', self.status.get(), 'success')
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
                self.dashboard.update_inputs(self.controller.objects, current)
                if self.capture:
                    capture = self.capture
                    names = self.capture_names(capture['baseline'], current)
                    # A button already held when capture began must be released
                    # and pressed again, rather than remaining permanently excluded.
                    for obj in self.controller.objects:
                        if obj.kind == 'button' and not current[obj.offset]:
                            capture['baseline'][obj.offset] = False
                    for name in names:
                        if name not in capture['names']:
                            capture['names'].append(name)
                            capture['settle'] = time.monotonic() + 0.65
                    if names and not capture.get('search'):
                        capture['modifiers'] |= self.keyboard_modifiers()
                    countdown = max(0, math.ceil(capture['deadline'] - time.monotonic()))
                    search = capture.get('search')
                    progress = f'{self.recording["index"] + 1}/{len(self.recording["targets"])} · ' if self.recording else ''
                    self.feedback(('FIND INPUT' if search else 'RECORDING') + f' · LISTENING · {countdown}s',
                                  progress + (self.action_name(self.catalogue.actions[self.selected]) + ' · ' + capture['slot'] if not search else 'Find assigned actions') +
                                  ' · Move an axis or press buttons together. Escape cancels.', 'search' if search else 'listen',
                                  detected=' + '.join(self.input_display(name) for name in capture['names']))
                    if capture['settle'] is not None and time.monotonic() >= capture['settle']:
                        self.capture = None
                        pairs = [self.resolve_input(name) for name in capture['names']]
                        if capture.get('search') or all(pairs):
                            if capture.get('search'):
                                self.jump_to_names(capture['names'])
                            else:
                                self.bind(capture['slot'], pairs, modifiers=capture.get('modifiers', 0))
                                self.feedback('SAVED · NOT RECORDING', f'{capture["slot"]} binding saved for {self.action_name(self.catalogue.actions[self.selected])}. Export XML to save the profile.',
                                              'success', detected=' + '.join(self.input_display(pair[0]) for pair in pairs))
                            if self.recording:
                                self.recording['index'] += 1
                                self.recording['recorded'] += 1
                                self.recording['waiting'] = True
                                self.recording['stable_since'] = None
                                self.recording['last'] = dict(current)
                                self.recording['release_offsets'] = {obj.offset for obj in self.controller.objects if obj.kind == 'button' and obj.msfs_name() in capture['names']}
                                self.recording['hat_offsets'] = {obj.offset for obj in self.controller.objects if obj.kind == 'pov' and any(name.startswith(obj.msfs_name() + ' ') for name in capture['names'])}
                                self.status.set('Binding recorded. Release buttons and let the axes settle before the next action.')
                                self.feedback('GUIDED RECORDING · WAITING FOR RELEASE', self.status.get(), 'listen')
                        else:
                            missing = ', '.join(name for name, pair in zip(capture['names'], pairs) if pair is None)
                            self.status.set(f'Detected {missing}; export blocked for this input until its ID is learned from a real XML.')
                            self.capture_result = 'retry'
                            self.feedback('INPUT DETECTED · ID NEEDED · NOT RECORDING',
                                          f'{missing}. Open a simulator export containing this input to learn its ID, then Try again. The binding was not changed.', 'error')
                    elif time.monotonic() >= capture['deadline']:
                        self.capture = None
                        self.capture_result = 'retry'
                        self.status.set('No new input detected. Release held buttons first; move an axis farther, then Try again. No binding was changed.')
                        self.feedback('TIMED OUT · NOT RECORDING', self.status.get(), 'error')
                elif self.recording and self.recording['waiting']:
                    session = self.recording
                    released = all(not current[offset] for offset in session.get('release_offsets', set()))
                    hats_centered = all(current[offset] < 0 for offset in session.get('hat_offsets', set()))
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
                elif self.follow_input.get():
                    names = self.capture_names(self.follow_baseline, current)
                    for obj in self.controller.objects:
                        if obj.kind != 'axis':
                            self.follow_baseline[obj.offset] = current[obj.offset]
                    if names:
                        if self.follow_pending is None:
                            self.follow_pending = {'names': [], 'settle': time.monotonic() + .3}
                        for name in names:
                            if name not in self.follow_pending['names']:
                                self.follow_pending['names'].append(name)
                        self.detected_input.set('Detected input: ' + ' + '.join(self.follow_pending['names']))
                    if self.follow_pending and time.monotonic() >= self.follow_pending['settle']:
                        names = self.follow_pending['names']
                        self.follow_pending = None
                        self.follow_baseline = dict(current)
                        self.jump_to_names(names)
            except OSError as exc:
                self.cancel_capture()
                self.status.set(f'{exc} Reconnect the controller and click Refresh.')
                self.feedback('CONTROLLER DISCONNECTED · NOT RECORDING', self.status.get(), 'error', detected='')
                self.controller.close()
                self.controller = None
                self.feedback('DISCONNECTED · NOT RECORDING', self.status.get(), 'error')
                self.dashboard.update_inputs([], {})
                self.update_binding_buttons()
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
        self.cancel_capture()
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
            from .local_profiles import is_managed_save
            if is_managed_save(path):
                raise ValueError('Choose an export folder outside the simulator’s managed saves. Import the exported XML through MSFS Controls.')
            self.profile.save(path)
            sidecar = Path(path).with_suffix('.studio.json')
            guid = self.label_guid(self.profile.device.attrib).lower()
            labels = self.labels.devices.get(guid, {})
            if labels or sidecar.is_file():
                sidecar.write_text(json.dumps({'controller_labels': {guid: labels}}, indent=2), encoding='utf-8')
            self.path, self.saved_text = Path(path), self.profile.to_text()
            self.status.set(f'Exported {self.path.name}. In MSFS: Settings → Controls → this controller → matching profile cogwheel → Import.')
            self.feedback('EXPORTED · NOT RECORDING', self.status.get(), 'success')
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
            f'{len(self.catalogue.actions):,} action/context entries from real exports, with English names where references supply them. Import reference profiles or an ActionDB to extend the catalogue.\n\n'
            'Windows inputs without a verified MSFS ID require a real reference export. XInput-only, VR and proprietary controls are not yet validated. CompositeID defaults to 0 for newly detected controllers; use a real export for composite-device metadata.\n\n'
            'The supported delivery route is XML import. Community-package installation needs separate validation and is not enabled. This build has not been tested in MSFS yet.\n\n'
            f'Detected Community folders:\n{folders}', parent=self.root)

    def close(self):
        for editor in self.sdk_editors:
            if editor.window.winfo_exists() and not editor.can_close():
                return
        if not self.can_discard():
            return
        self.profile_scan_cancel.set()
        if self.controller:
            self.controller.close()
        if self.backend:
            self.backend.close()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
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
