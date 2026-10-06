"""Native Windows DirectInput enumeration and capture, with no simulator process."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass, field
import os
import struct
import uuid

from .profiles import AXES

DWORD, WORD, LONG = C.c_uint32, C.c_uint16, C.c_int32
CALL = getattr(C, 'WINFUNCTYPE', C.CFUNCTYPE)


class GUID(C.Structure):
    _fields_ = [('Data1', DWORD), ('Data2', WORD), ('Data3', WORD), ('Data4', C.c_ubyte * 8)]

    @classmethod
    def from_string(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value.strip('{}')).bytes_le)

    def __str__(self):
        return '{' + str(uuid.UUID(bytes_le=bytes(self))) + '}'


class DeviceInstance(C.Structure):
    _fields_ = [('size', DWORD), ('instance', GUID), ('product', GUID), ('type', DWORD),
                ('instance_name', C.c_wchar * 260), ('product_name', C.c_wchar * 260),
                ('ff', GUID), ('usage_page', WORD), ('usage', WORD)]


class ObjectInstance(C.Structure):
    _fields_ = [('size', DWORD), ('guid', GUID), ('offset', DWORD), ('type', DWORD),
                ('flags', DWORD), ('name', C.c_wchar * 260), ('ff_max', DWORD),
                ('ff_resolution', DWORD), ('collection', WORD), ('designator', WORD),
                ('usage_page', WORD), ('usage', WORD), ('dimension', DWORD),
                ('exponent', WORD), ('report', WORD)]


class ObjectFormat(C.Structure):
    _fields_ = [('guid', C.POINTER(GUID)), ('offset', DWORD), ('type', DWORD), ('flags', DWORD)]


class DataFormat(C.Structure):
    _fields_ = [('size', DWORD), ('object_size', DWORD), ('flags', DWORD),
                ('data_size', DWORD), ('object_count', DWORD), ('objects', C.POINTER(ObjectFormat))]


class PropertyRange(C.Structure):
    _fields_ = [('size', DWORD), ('header_size', DWORD), ('object', DWORD),
                ('how', DWORD), ('minimum', LONG), ('maximum', LONG)]


def method(pointer, index, result=LONG, *args):
    vtable = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    return CALL(result, C.c_void_p, *args)(vtable[index])


def check(hr, operation):
    if hr < 0:
        raise OSError(f'{operation} failed (DirectInput 0x{hr & 0xffffffff:08X}).')


@dataclass
class InputObject:
    kind: str
    index: int
    name: str
    offset: int
    type: int
    guid: GUID = field(repr=False)
    axis: str = ''

    def msfs_name(self, direction=''):
        if self.kind == 'button':
            return f'Joystick Button {self.index + 1}'
        if self.kind == 'pov':
            number = f' {self.index + 1}' if self.index else ''
            return f'Joystick Pov{number} {direction}'.strip()
        prefix = {'X': 'L-Axis X', 'Y': 'L-Axis Y', 'Z': 'L-Axis Z',
                  'rX': 'R-Axis X', 'rY': 'R-Axis Y', 'rZ': 'R-Axis Z',
                  'SliderX': 'Slider X', 'SliderY': 'Slider Y'}[self.axis]
        return f'Joystick {prefix}{direction}'


@dataclass
class Device:
    name: str
    instance_guid: str
    product_guid: str
    product_id: int
    vendor_id: int
    objects: list = field(default_factory=list)

    @property
    def attributes(self):
        return {'DeviceName': self.name, 'GUID': self.instance_guid,
                'ProductID': str(self.product_id), 'CompositeID': '0', 'HWVer': '1.0.0.0'}


class DirectInput:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Controller capture is available on Windows only.')
        self.library = C.WinDLL('dinput8.dll')
        self.pointer = C.c_void_p()
        kernel = C.WinDLL('kernel32.dll')
        kernel.GetModuleHandleW.restype = C.c_void_p
        create = self.library.DirectInput8Create
        create.argtypes = [C.c_void_p, DWORD, C.POINTER(GUID), C.POINTER(C.c_void_p), C.c_void_p]
        create.restype = LONG
        iid = GUID.from_string('BF798031-483A-4DA2-AA99-5D64ED369700')
        check(create(kernel.GetModuleHandleW(None), 0x0800, C.byref(iid), C.byref(self.pointer), None), 'Initialize')

    def enumerate(self):
        devices = []
        callback_type = CALL(C.c_int, C.POINTER(DeviceInstance), C.c_void_p)

        def found(info, _):
            d = info.contents
            devices.append(Device(d.product_name, str(d.instance), str(d.product),
                                  d.product.Data1 >> 16, d.product.Data1 & 0xffff))
            return 1

        callback = callback_type(found)
        check(method(self.pointer, 4, LONG, DWORD, callback_type, C.c_void_p, DWORD)(
            self.pointer, 4, callback, None, 1), 'Enumerate controllers')
        return devices

    def open(self, device, hwnd):
        return Controller(self, device, hwnd)

    def close(self):
        if self.pointer:
            method(self.pointer, 2, DWORD)(self.pointer)
            self.pointer = C.c_void_p()


class Controller:
    DATA_SIZE = 176  # 8 axes, 4 hats, 128 buttons

    def __init__(self, backend, device, hwnd):
        self.pointer = C.c_void_p()
        self.device = device
        self.objects = []
        guid = GUID.from_string(device.instance_guid)
        check(method(backend.pointer, 3, LONG, C.POINTER(GUID), C.POINTER(C.c_void_p), C.c_void_p)(
            backend.pointer, C.byref(guid), C.byref(self.pointer), None), 'Open controller')
        try:
            self._configure(hwnd)
        except Exception:
            self.close()
            raise

    def _configure(self, hwnd):
        callback_type = CALL(C.c_int, C.POINTER(ObjectInstance), C.c_void_p)
        slider_count = 0

        def found(info, _):
            nonlocal slider_count
            obj = info.contents
            kind = obj.type & 0xff
            index = (obj.type >> 8) & 0xffff
            saved_guid = GUID.from_buffer_copy(bytes(obj.guid))
            if kind & 0x3:  # axis
                axis = {0x30: 'X', 0x31: 'Y', 0x32: 'Z', 0x33: 'rX', 0x34: 'rY', 0x35: 'rZ'}.get(obj.usage)
                if axis is None:
                    axis = {0xa36d02e0: 'X', 0xa36d02e1: 'Y', 0xa36d02e2: 'Z',
                            0xa36d02f4: 'rX', 0xa36d02f5: 'rY', 0xa36d02e3: 'rZ'}.get(obj.guid.Data1)
                if axis is None and (obj.usage in (0x36, 0x37) or obj.guid.Data1 == 0xa36d02e4):
                    if slider_count >= 2:
                        return 1
                    axis = ('SliderX', 'SliderY')[slider_count]
                    slider_count += 1
                if axis and not any(o.axis == axis for o in self.objects):
                    self.objects.append(InputObject('axis', index, obj.name, AXES.index(axis) * 4, obj.type, saved_guid, axis))
            elif kind & 0xc and index < 128:
                self.objects.append(InputObject('button', index, obj.name, 48 + index, obj.type, saved_guid))
            elif kind & 0x10 and index < 4:
                self.objects.append(InputObject('pov', index, obj.name, 32 + index * 4, obj.type, saved_guid))
            return 1

        callback = callback_type(found)
        check(method(self.pointer, 4, LONG, callback_type, C.c_void_p, DWORD)(self.pointer, callback, None, 0), 'Read controller inputs')
        self.objects.sort(key=lambda o: (('axis', 'pov', 'button').index(o.kind), o.offset))
        self.device.objects = self.objects
        self.guid_refs = [obj.guid for obj in self.objects]
        self.formats = (ObjectFormat * len(self.objects))(*[
            ObjectFormat(C.pointer(obj.guid), obj.offset, obj.type, 0) for obj in self.objects])
        self.format = DataFormat(C.sizeof(DataFormat), C.sizeof(ObjectFormat), 1, self.DATA_SIZE, len(self.objects), self.formats)
        check(method(self.pointer, 11, LONG, C.POINTER(DataFormat))(self.pointer, C.byref(self.format)), 'Configure controller')
        check(method(self.pointer, 13, LONG, C.c_void_p, DWORD)(self.pointer, hwnd, 0xa), 'Set background access')
        for obj in self.objects:
            if obj.kind == 'axis':
                limits = PropertyRange(C.sizeof(PropertyRange), 16, obj.offset, 1, -32768, 32767)
                check(method(self.pointer, 6, LONG, C.c_void_p, C.c_void_p)(self.pointer, 4, C.byref(limits)), 'Set axis range')
        check(method(self.pointer, 7)(self.pointer), 'Acquire controller')

    def read(self):
        # Poll and reacquire after reconnect or a foreground application takes access.
        hr = method(self.pointer, 25)(self.pointer)
        if hr < 0:
            method(self.pointer, 7)(self.pointer)
            method(self.pointer, 25)(self.pointer)
        buffer = (C.c_ubyte * self.DATA_SIZE)()
        check(method(self.pointer, 9, LONG, DWORD, C.c_void_p)(self.pointer, self.DATA_SIZE, C.byref(buffer)), 'Read controller')
        raw = bytes(buffer)
        values = {}
        for obj in self.objects:
            if obj.kind == 'axis':
                values[obj.offset] = max(-1.0, min(1.0, struct.unpack_from('<i', raw, obj.offset)[0] / 32768))
            elif obj.kind == 'button':
                values[obj.offset] = bool(raw[obj.offset] & 0x80)
            else:
                angle = struct.unpack_from('<I', raw, obj.offset)[0]
                values[obj.offset] = -1 if angle & 0xffff == 0xffff else angle
        return values

    def close(self):
        if self.pointer:
            method(self.pointer, 8)(self.pointer)
            method(self.pointer, 2, DWORD)(self.pointer)
            self.pointer = C.c_void_p()


POV_DIRECTIONS = ('Up', 'Up_Right', 'Right', 'Down_Right', 'Down', 'Down_Left', 'Left', 'Up_Left')


def changed_inputs(objects, baseline, current, split_axes=False):
    """Buttons on rising edge, hats on direction change, axes beyond noise threshold."""
    detected = []
    for obj in objects:
        if obj.offset not in baseline or obj.offset not in current:
            continue
        before, now = baseline[obj.offset], current[obj.offset]
        if obj.kind == 'button' and now and not before:
            detected.append(obj.msfs_name())
        elif obj.kind == 'axis' and abs(now - before) >= 0.18:
            detected.append(obj.msfs_name(('+' if now > before else '-') if split_axes else ''))
        elif obj.kind == 'pov' and now != before and now >= 0:
            detected.append(obj.msfs_name(POV_DIRECTIONS[int((now + 2250) // 4500) % 8]))
    return detected
