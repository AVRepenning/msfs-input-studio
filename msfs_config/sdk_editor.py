"""Structured forms for documented SDK input sources, with semantic preservation."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET

from .sdk import SDKDocument, ATTRIBUTES, CHILDREN, ACTION_FIELDS


class SDKEditor:
    def __init__(self, app, document):
        self.app, self.document = app, document
        self.undo_states, self.redo_states = [], []
        self.node, self.fields = None, {}
        self.window = tk.Toplevel(app.root)
        self.window.title('SDK source editor · ' + document.root.tag)
        self.window.geometry('960x740')
        self.saved = document.to_text()
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        shell = ttk.Frame(self.window, padding=16)
        shell.pack(fill='both', expand=True)
        ttk.Label(shell, text=document.root.tag + ' source', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(shell, text='Edit package sources here. Use the MSFS SDK to build and test the package before installation.',
                  style='Muted.TLabel', wraplength=870).pack(anchor='w', pady=6)
        bar = ttk.Frame(shell)
        bar.pack(fill='x', pady=6)
        for title, callback in [('Open source', self.open), ('Save source as…', self.save),
                                ('Validate', self.validate), ('Undo', self.undo), ('Redo', self.redo)]:
            ttk.Button(bar, text=title, command=callback).pack(side='left', padx=(0, 5))
        if document.root.tag == 'ActionDefinition':
            ttk.Button(bar, text='Use these controls', command=self.use_controls).pack(side='left')
        body = ttk.Panedwindow(shell, orient='horizontal')
        body.pack(fill='both', expand=True, pady=8)
        left, right = ttk.Frame(body), ttk.Frame(body)
        body.add(left, weight=2)
        body.add(right, weight=3)
        self.tree = ttk.Treeview(left, show='tree', selectmode='browse')
        scroll = ttk.Scrollbar(left, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.form = ttk.Frame(right, padding=(12, 0, 0, 0))
        self.form.pack(fill='both', expand=True)
        actions = ttk.Frame(shell)
        actions.pack(fill='x')
        ttk.Label(actions, text='Add child to selected item').pack(side='left')
        self.child = tk.StringVar()
        self.child_combo = ttk.Combobox(actions, textvariable=self.child, state='readonly', width=20)
        self.child_combo.pack(side='left', padx=6)
        ttk.Button(actions, text='Add', command=self.add).pack(side='left')
        ttk.Button(actions, text='Remove selected', command=self.remove).pack(side='left', padx=6)
        ttk.Button(actions, text='Apply fields', command=self.apply).pack(side='right')
        self.status = tk.StringVar(value='Fields apply when you select another item or save. Unknown XML content is retained.')
        ttk.Label(shell, textvariable=self.status, wraplength=880, style='Muted.TLabel').pack(fill='x', pady=(10, 0))
        self.refresh(document.root)

    def refresh(self, target=None):
        self.node, self.fields = None, {}
        self.tree.delete(*self.tree.get_children())
        self.nodes = {}
        def insert(node, parent=''):
            if not isinstance(node.tag, str):
                return
            title = node.tag
            name = node.get('DisplayName') or node.get('str') or node.get('buttonId') or node.findtext('Name') or node.get('Name')
            if name:
                title += ' · ' + name
            elif node.text and node.text.strip():
                title += ' · ' + node.text.strip()[:75]
            row = self.tree.insert(parent, 'end', text=title, open=node.tag != 'Action')
            self.nodes[row] = node
            if node is target:
                self.tree.selection_set(row)
                self.tree.focus(row)
                self.tree.see(row)
            for child in node:
                insert(child, row)
        insert(self.document.root)
        self.select()

    def snapshot(self):
        self.undo_states.append(self.document.to_text())
        self.redo_states.clear()

    def apply(self):
        if self.node is None:
            return
        before = self.document.to_text()
        for (kind, name), var in self.fields.items():
            value = var.get()
            if kind == 'attribute':
                if value:
                    self.node.set(name, value)
                else:
                    self.node.attrib.pop(name, None)
            elif kind == 'child':
                child = self.node.find(name)
                if child is None and value:
                    child = ET.SubElement(self.node, name)
                if child is not None:
                    child.text = value
            else:
                self.node.text = value or None
        if before != self.document.to_text():
            self.undo_states.append(before)
            self.redo_states.clear()
            self.status.set('Fields applied. Save source as… writes the SDK source file.')

    def select(self, _=None):
        selection = self.tree.selection()
        if not selection:
            return
        node = self.nodes.get(selection[0])
        if node is self.node:
            return
        self.apply()
        self.node, self.fields = node, {}
        for widget in self.form.winfo_children():
            widget.destroy()
        if node is None:
            return
        ttk.Label(self.form, text=node.tag, style='Heading.TLabel').pack(anchor='w', pady=(0, 10))
        attributes = tuple(dict.fromkeys(ATTRIBUTES.get(node.tag, ()) + tuple(node.attrib)))
        for name in attributes:
            self.field('attribute', name, node.get(name, ''))
        if node.tag == 'Action' and self.document.root.tag == 'ActionDefinition':
            for name in ACTION_FIELDS:
                self.field('child', name, node.findtext(name, ''))
        elif not len(node) or (node.text and node.text.strip()):
            self.field('text', 'Text / input name', (node.text or '').strip())
        children = CHILDREN.get(node.tag, ())
        self.child_combo.configure(values=children)
        self.child.set(children[0] if children else '')
        if node.tag == 'InputAction':
            ttk.Label(self.form, text='Inputs inside this alternative are combined with AND. Separate InputAction alternatives use OR.',
                      wraplength=440, style='Muted.TLabel').pack(anchor='w', pady=10)

    def field(self, kind, name, value):
        row = ttk.Frame(self.form)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text=name, width=21).pack(side='left')
        var = tk.StringVar(value=value)
        ttk.Entry(row, textvariable=var).pack(side='left', fill='x', expand=True)
        self.fields[(kind, name)] = var

    def add(self):
        if self.node is None or self.child.get() not in CHILDREN.get(self.node.tag, ()):
            return
        self.apply()
        self.snapshot()
        node = ET.SubElement(self.node, self.child.get())
        if node.tag == 'Action':
            for field, value in [('Context', 'INPUT_EVENTS'), ('Type', 'DIGITAL'), ('TT_Name', ''),
                                 ('TT_Category_Main', ''), ('TT_Category_Sub', '')]:
                ET.SubElement(node, field).text = value
        elif node.tag == 'RemapAction':
            node.set('player', 'ALL')
        self.refresh(node)

    def remove(self):
        if self.node is None or self.node is self.document.root:
            return
        self.apply()
        parent = next((n for n in self.document.root.iter() if self.node in list(n)), None)
        if parent is not None:
            self.snapshot()
            parent.remove(self.node)
            self.refresh(parent)

    def validate(self):
        self.apply()
        errors = self.document.validate()
        self.status.set('\n'.join(errors[:6]) if errors else 'Document structure passed local validation. Simulator build and runtime testing are still required.')
        return not errors

    def save(self):
        self.apply()
        if not self.validate():
            return
        name = {'DeviceConfig': 'DeviceConfig.xml', 'ActionDefinition': 'action.actiondb', 'RemapActions': 'remapAction.remapdb'}[self.document.root.tag]
        path = filedialog.asksaveasfilename(parent=self.window, initialfile=name, defaultextension='.' + name.rsplit('.', 1)[1])
        if path:
            try:
                self.document.save(path)
                self.saved = self.document.to_text()
                self.status.set('Saved SDK source: ' + path)
            except (OSError, ValueError) as exc:
                messagebox.showerror('SDK source editor', str(exc), parent=self.window)

    def open(self):
        if not self.can_close():
            return
        path = filedialog.askopenfilename(parent=self.window, filetypes=[('SDK XML sources', '*.xml *.actiondb *.remapdb'), ('All files', '*.*')])
        if path:
            try:
                document = SDKDocument.load(path)
                if document.root.tag != self.document.root.tag:
                    raise ValueError('Open a ' + self.document.root.tag + ' source in this editor.')
                self.document = document
                self.saved = document.to_text()
                self.undo_states, self.redo_states = [], []
                self.refresh(document.root)
            except (OSError, ValueError, ET.ParseError) as exc:
                messagebox.showerror('SDK source editor', str(exc), parent=self.window)

    def use_controls(self):
        self.apply()
        if self.validate():
            self.app.import_action_document(self.document)

    def undo(self):
        self.apply()
        if self.undo_states:
            self.redo_states.append(self.document.to_text())
            self.document = SDKDocument.from_text(self.undo_states.pop())
            self.refresh(self.document.root)

    def redo(self):
        if self.redo_states:
            self.undo_states.append(self.document.to_text())
            self.document = SDKDocument.from_text(self.redo_states.pop())
            self.refresh(self.document.root)

    def can_close(self):
        self.apply()
        return self.saved == self.document.to_text() or messagebox.askyesno('Unsaved SDK source', 'Discard unsaved SDK source changes?', parent=self.window)

    def close(self):
        if self.can_close():
            self.window.destroy()
