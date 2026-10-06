"""Windows keyboard/mouse capture, enabled using real MSFS profile references."""
import ctypes as C
from dataclasses import dataclass, field

from .catalogue import device_family


@dataclass
class SystemObject:
    name: str
    information: str
    offset: int
    kind: str = 'button'
    index: int = 0
    axis: str = ''
    family: str = ''
    derived: bool = False

    def msfs_name(self, direction=''):
        if self.family == 'gamepad' and self.information in ('LT', 'RT'):
            return self.information
        if self.family == 'gamepad' and direction and self.information.startswith(('LS ', 'RS ')):
            return self.information[:2] + ' ' + ({'X': ('Left', 'Right'), 'Y': ('Down', 'Up')}[self.information[-1]][direction == '+'])
        return self.information + direction


@dataclass
class SystemDevice:
    name: str
    source_attributes: dict
    family: str
    references: dict
    objects: list = field(default_factory=list)
    vendor_id: int = 0
    product_guid: str = ''
    slot: int = 0

    @property
    def instance_guid(self):
        return self.source_attributes.get('GUID', '{0}')

    @property
    def product_id(self):
        value = self.source_attributes.get('ProductID', '0')
        return int(value, 16 if value.lower().startswith('0x') else 10)

    @property
    def attributes(self):
        return dict(self.source_attributes)


def system_devices(profiles, catalogue):
    found = {}
    for profile in profiles:
        family = device_family(profile.device.attrib)
        if family in ('keyboard', 'mouse', 'gamepad') and profile.device.get('GUID') == '{0}' and family not in found:
            found[family] = SystemDevice('Windows ' + family.title(), dict(profile.device.attrib), family,
                                         dict(catalogue.keys_for(family)))
    result = [device for family, device in found.items() if family != 'gamepad']
    if 'gamepad' in found:
        try:
            api = xinput_api()
            prototype = found['gamepad']
            for slot in range(4):
                state = XInputState()
                if api.XInputGetState(slot, C.byref(state)) == 0:
                    result.append(SystemDevice(f'Windows XInput gamepad {slot + 1}', dict(prototype.attributes), 'gamepad', dict(prototype.references), slot=slot))
        except OSError:
            pass
    return result


class XInputGamepad(C.Structure):
    _fields_ = [('buttons', C.c_uint16), ('lt', C.c_ubyte), ('rt', C.c_ubyte),
                ('lx', C.c_int16), ('ly', C.c_int16), ('rx', C.c_int16), ('ry', C.c_int16)]


class XInputState(C.Structure):
    _fields_ = [('packet', C.c_uint32), ('pad', XInputGamepad)]


def xinput_api():
    try:
        api = C.WinDLL('xinput1_4.dll')
    except OSError:
        api = C.WinDLL('xinput9_1_0.dll')
    api.XInputGetState.argtypes = [C.c_uint32, C.POINTER(XInputState)]
    api.XInputGetState.restype = C.c_uint32
    return api


class XInputController:
    BUTTONS = {'A': 0x1000, 'B': 0x2000, 'X': 0x4000, 'Y': 0x8000, 'LB': 0x100, 'RB': 0x200,
               'BACK': 0x20, 'START': 0x10, 'LS': 0x40, 'RS': 0x80,
               'D-PAD Up': 1, 'D-PAD Down': 2, 'D-PAD Left': 4, 'D-PAD Right': 8}
    AXES = [('LS X', 'X', 'lx'), ('LS Y', 'Y', 'ly'), ('RS X', 'rX', 'rx'),
            ('RS Y', 'rY', 'ry'), ('LT', 'Z', 'lt'), ('RT', 'rZ', 'rt')]

    def __init__(self, device):
        self.device, self.api, self.objects = device, xinput_api(), []
        for index, name in enumerate(self.BUTTONS):
            self.objects.append(SystemObject(name, name, index, index=index, family='gamepad'))
        for index, (name, axis, _) in enumerate(self.AXES):
            self.objects.append(SystemObject(name, name, 20 + index, kind='axis', index=index, axis=axis, family='gamepad'))
        for index, name in enumerate(f'{stick} {direction}' for stick in ('LS', 'RS') for direction in ('Left', 'Right', 'Up', 'Down')):
            self.objects.append(SystemObject(name, name, 30 + index, index=14 + index, family='gamepad', derived=True))
        device.objects = self.objects

    def read(self):
        state = XInputState()
        if self.api.XInputGetState(self.device.slot, C.byref(state)):
            raise OSError('XInput gamepad disconnected.')
        pad = state.pad
        result = {index: bool(pad.buttons & mask) for index, mask in enumerate(self.BUTTONS.values())}
        for index, (_, _, attr) in enumerate(self.AXES):
            value = getattr(pad, attr)
            result[20 + index] = value / 255 if attr in ('lt', 'rt') else value / (32768 if value < 0 else 32767)
        directions = (pad.lx < -8192, pad.lx > 8192, pad.ly > 8192, pad.ly < -8192,
                      pad.rx < -8192, pad.rx > 8192, pad.ry > 8192, pad.ry < -8192)
        result.update({30 + index: bool(pressed) for index, pressed in enumerate(directions)})
        return result

    def close(self):
        pass


class SystemController:
    def __init__(self, device):
        self.device, self.objects = device, []
        self.api = C.WinDLL('user32.dll')
        self.api.GetAsyncKeyState.argtypes = [C.c_int]
        self.api.GetAsyncKeyState.restype = C.c_short
        self.api.GetKeyNameTextW.argtypes = [C.c_long, C.c_wchar_p, C.c_int]
        self.api.MapVirtualKeyW.argtypes = [C.c_uint, C.c_uint]
        self.pending_wheel = None
        if device.family == 'keyboard':
            by_id = {value: name for name, value in device.references.items() if 8 <= value <= 254}
            for vk in range(8, 255):
                if vk in (16, 17, 18):  # Avoid duplicating left/right modifiers.
                    continue
                buffer = C.create_unicode_buffer(100)
                scan = self.api.MapVirtualKeyW(vk, 4)
                extended = vk in (33, 34, 35, 36, 37, 38, 39, 40, 45, 46, 111, 163, 165)
                self.api.GetKeyNameTextW(((scan & 255) << 16) | (1 << 24 if extended else 0), buffer, 100)
                if not buffer.value and vk not in by_id:
                    continue
                name = buffer.value or f'VK {vk}'
                information = by_id.get(vk, f'Keyboard VK {vk}')
                self.objects.append(SystemObject(name, information, vk, index=vk - 1, family='keyboard'))
        else:
            names = ('Left-Click', 'Right-Click', 'Mid-Click', 'Mouse 4', 'Mouse 5', 'Mouse Wheel Up', 'Mouse Wheel Down')
            for index, name in enumerate(names):
                self.objects.append(SystemObject(name, name, index, index=index, family='mouse'))
            for index, axis in enumerate(('X', 'Y')):
                self.objects.append(SystemObject('Mouse ' + axis, 'Axis ' + axis, 7 + index, kind='axis', index=index, axis=axis, family='mouse'))
            self.reset_baseline()
        device.objects = self.objects

    def reset_baseline(self):
        if self.device.family == 'mouse':
            point = (C.c_long * 2)()
            self.api.GetCursorPos(C.byref(point))
            self.origin = tuple(point)

    def wheel(self, delta):
        self.pending_wheel = 5 if delta > 0 else 6

    def read(self):
        if self.device.family == 'keyboard':
            return {o.offset: bool(self.api.GetAsyncKeyState(o.offset) & 0x8000) for o in self.objects}
        point = (C.c_long * 2)()
        self.api.GetCursorPos(C.byref(point))
        result = {index: bool(self.api.GetAsyncKeyState(vk) & 0x8000)
                  for index, vk in enumerate((1, 2, 4, 5, 6))}
        result.update({5: self.pending_wheel == 5, 6: self.pending_wheel == 6,
                       7: max(-1, min(1, (point[0] - self.origin[0]) / 200)),
                       8: max(-1, min(1, (point[1] - self.origin[1]) / 200))})
        self.pending_wheel = None
        return result

    def close(self):
        pass
