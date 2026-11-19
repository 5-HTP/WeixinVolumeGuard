import ctypes as C
from ctypes import wintypes as W
import hashlib
import os
from pathlib import Path
import struct

kernel = C.WinDLL("kernel32", use_last_error=True)
advapi = C.WinDLL("advapi32", use_last_error=True)
version_api = C.WinDLL("version", use_last_error=True)
HANDLE = W.HANDLE
kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel.OpenProcess.restype = HANDLE
kernel.CloseHandle.argtypes = [HANDLE]
kernel.GetCurrentProcess.restype = HANDLE
advapi.OpenProcessToken.argtypes = [HANDLE, W.DWORD, C.POINTER(HANDLE)]
advapi.GetTokenInformation.argtypes = [HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
advapi.ConvertSidToStringSidW.argtypes = [C.c_void_p, C.POINTER(W.LPWSTR)]
kernel.LocalFree.argtypes = [C.c_void_p]
kernel.ProcessIdToSessionId.argtypes = [W.DWORD, C.POINTER(W.DWORD)]
kernel.GetProcessTimes.argtypes = [HANDLE] + [C.POINTER(W.FILETIME)] * 4
kernel.K32EnumProcessModulesEx.argtypes = [HANDLE, C.POINTER(HANDLE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
kernel.K32GetModuleFileNameExW.argtypes = [HANDLE, HANDLE, W.LPWSTR, W.DWORD]
version_api.GetFileVersionInfoSizeW.argtypes = [W.LPCWSTR, C.POINTER(W.DWORD)]
version_api.GetFileVersionInfoW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p]
version_api.VerQueryValueW.argtypes = [C.c_void_p, W.LPCWSTR, C.POINTER(C.c_void_p), C.POINTER(W.UINT)]


def checked(ok):
    if not ok:
        raise C.WinError(C.get_last_error())


def process_handle(pid, access=0x1410):
    handle = kernel.OpenProcess(access, False, pid)
    checked(handle)
    return handle


def sid(pid):
    handle = process_handle(pid, 0x1000)
    token = HANDLE()
    try:
        checked(advapi.OpenProcessToken(handle, 8, C.byref(token)))
        size = W.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, C.byref(size))
        buffer = C.create_string_buffer(size.value)
        checked(advapi.GetTokenInformation(token, 1, buffer, size, C.byref(size)))
        pointer = C.cast(buffer, C.POINTER(C.c_void_p))[0]
        value = W.LPWSTR()
        checked(advapi.ConvertSidToStringSidW(pointer, C.byref(value)))
        try:
            return value.value
        finally:
            kernel.LocalFree(C.cast(value, C.c_void_p))
    finally:
        if token:
            kernel.CloseHandle(token)
        kernel.CloseHandle(handle)


def session_id(pid):
    value = W.DWORD()
    checked(kernel.ProcessIdToSessionId(pid, C.byref(value)))
    return value.value


def creation_time(pid):
    handle = process_handle(pid, 0x1000)
    try:
        times = [W.FILETIME() for _ in range(4)]
        checked(kernel.GetProcessTimes(handle, *(C.byref(t) for t in times)))
        return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


def modules(pid):
    handle = process_handle(pid)
    try:
        array = (HANDLE * 2048)()
        size = W.DWORD()
        checked(kernel.K32EnumProcessModulesEx(handle, array, C.sizeof(array), C.byref(size), 3))
        if size.value > C.sizeof(array):
            raise RuntimeError("ModuleListTooLarge")
        result = []
        for item in array[:size.value // C.sizeof(HANDLE)]:
            buffer = C.create_unicode_buffer(32768)
            checked(kernel.K32GetModuleFileNameExW(handle, item, buffer, len(buffer)))
            result.append((buffer.value, item))
        return result
    finally:
        kernel.CloseHandle(handle)


def file_version(path):
    unused = W.DWORD()
    size = version_api.GetFileVersionInfoSizeW(str(path), C.byref(unused))
    checked(size)
    data = C.create_string_buffer(size)
    checked(version_api.GetFileVersionInfoW(str(path), 0, size, data))
    pointer = C.c_void_p()
    length = W.UINT()
    checked(version_api.VerQueryValueW(data, "\\", C.byref(pointer), C.byref(length)))
    fields = C.cast(pointer, C.POINTER(W.DWORD))
    return ".".join(str(x) for x in (fields[2] >> 16, fields[2] & 65535, fields[3] >> 16, fields[3] & 65535))


def file_identity(path):
    st = os.stat(path)
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def inspect_file(path):
    before = file_identity(path)
    with open(path, "rb") as stream:
        header = stream.read(4096)
        offset = struct.unpack_from("<I", header, 60)[0]
        if header[:2] != b"MZ" or header[offset:offset + 4] != b"PE\0\0":
            raise RuntimeError("InvalidPE")
        machine = struct.unpack_from("<H", header, offset + 4)[0]
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest().upper()
    value = file_version(path)
    if before != file_identity(path):
        raise RuntimeError("ModuleChanged")
    return value, digest, machine, before


def system_directory():
    buffer = C.create_unicode_buffer(32768)
    checked(kernel.GetSystemDirectoryW(buffer, len(buffer)))
    return buffer.value
