from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import threading
import uuid


COINIT_APARTMENTTHREADED = 0x2
CLSCTX_INPROC_SERVER = 0x1
FOS_PICKFOLDERS = 0x20
FOS_FORCEFILESYSTEM = 0x40
FOS_PATHMUSTEXIST = 0x800
SIGDN_FILESYSPATH = 0x80058000
HRESULT_CANCELLED = 0x800704C7


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "GUID":
        guid = cls()
        ctypes.memmove(ctypes.byref(guid), uuid.UUID(value).bytes_le, 16)
        return guid


CLSID_FILE_OPEN_DIALOG = GUID.from_string("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
IID_FILE_OPEN_DIALOG = GUID.from_string("D57C7288-D4AD-4768-BE02-9D969532D960")
IID_SHELL_ITEM = GUID.from_string("43826D1E-E718-42EE-BC55-A1E261C37BFE")


def _failed(hresult: int) -> bool:
    return hresult < 0


def _cancelled(hresult: int) -> bool:
    return hresult & 0xFFFFFFFF == HRESULT_CANCELLED


def _com_method(instance: ctypes.c_void_p, index: int, *argtypes):
    vtable = ctypes.cast(
        instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    )[0]
    prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])


def _release(instance: ctypes.c_void_p) -> None:
    if instance:
        _com_method(instance, 2)(instance)


def _raise_for_hresult(hresult: int, operation: str) -> None:
    if _failed(hresult):
        raise OSError(f"{operation} failed with HRESULT 0x{hresult & 0xFFFFFFFF:08X}")


def _foreground_window_handle() -> int | None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    handle = user32.GetForegroundWindow()
    return int(handle) if handle else None


def _choose_folder_on_sta_thread(
    initial_directory: str,
    owner_window: int | None,
) -> str | None:
    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell32.SHCreateItemFromParsingName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    initialized = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    _raise_for_hresult(initialized, "CoInitializeEx")
    dialog = ctypes.c_void_p()

    try:
        _raise_for_hresult(
            ole32.CoCreateInstance(
                ctypes.byref(CLSID_FILE_OPEN_DIALOG),
                None,
                CLSCTX_INPROC_SERVER,
                ctypes.byref(IID_FILE_OPEN_DIALOG),
                ctypes.byref(dialog),
            ),
            "CoCreateInstance(IFileOpenDialog)",
        )

        _raise_for_hresult(
            _com_method(dialog, 9, wintypes.DWORD)(
                dialog, FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST
            ),
            "IFileDialog.SetOptions",
        )
        _raise_for_hresult(
            _com_method(dialog, 17, wintypes.LPCWSTR)(dialog, "选择存档文件夹"),
            "IFileDialog.SetTitle",
        )

        if initial_directory:
            folder = ctypes.c_void_p()
            create_folder_result = shell32.SHCreateItemFromParsingName(
                initial_directory,
                None,
                ctypes.byref(IID_SHELL_ITEM),
                ctypes.byref(folder),
            )
            if not _failed(create_folder_result):
                try:
                    _raise_for_hresult(
                        _com_method(dialog, 12, ctypes.c_void_p)(dialog, folder),
                        "IFileDialog.SetFolder",
                    )
                finally:
                    _release(folder)

        owner = wintypes.HWND(owner_window) if owner_window else None
        show_result = _com_method(dialog, 3, wintypes.HWND)(dialog, owner)
        if _cancelled(show_result):
            return None
        _raise_for_hresult(show_result, "IFileDialog.Show")

        selected_item = ctypes.c_void_p()
        _raise_for_hresult(
            _com_method(dialog, 20, ctypes.POINTER(ctypes.c_void_p))(
                dialog, ctypes.byref(selected_item)
            ),
            "IFileDialog.GetResult",
        )
        try:
            selected_path = ctypes.c_wchar_p()
            _raise_for_hresult(
                _com_method(selected_item, 5, wintypes.DWORD, ctypes.POINTER(ctypes.c_wchar_p))(
                    selected_item, SIGDN_FILESYSPATH, ctypes.byref(selected_path)
                ),
                "IShellItem.GetDisplayName",
            )
            try:
                return selected_path.value
            finally:
                ole32.CoTaskMemFree(ctypes.cast(selected_path, ctypes.c_void_p))
        finally:
            _release(selected_item)
    finally:
        _release(dialog)
        ole32.CoUninitialize()


def choose_folder(initial_directory: str = "") -> str | None:
    """Open the Windows Explorer-style folder picker used by modern applications."""
    if sys.platform != "win32":
        raise OSError("The modern Windows folder picker is only available on Windows.")

    result: dict[str, str | None] = {}
    error: list[BaseException] = []
    owner_window = _foreground_window_handle()

    def worker() -> None:
        try:
            result["path"] = _choose_folder_on_sta_thread(
                initial_directory,
                owner_window,
            )
        except BaseException as exception:
            error.append(exception)

    thread = threading.Thread(target=worker, name="WindowsFolderPicker")
    thread.start()
    thread.join()

    if error:
        raise error[0]
    return result.get("path")
