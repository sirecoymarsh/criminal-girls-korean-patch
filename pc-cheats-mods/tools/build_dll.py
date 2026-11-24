"""Build the proxy xinput1_3.dll (i686, no CRT) -> pc/build/xinput1_3.dll"""
import subprocess
from pathlib import Path

ROOT = Path(r"P:\AI\cg-battle-subs\pc")
BIN = Path(r"P:\AI\toolchains\winlibs\mingw64\bin")
OUT = ROOT / "build"
TARGET = "--target=i686-pc-windows-msvc"
CFLAGS = [TARGET, "-O2", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-exceptions",
          "-fno-asynchronous-unwind-tables", "-mno-sse4", "-msse2", "-Wall", "-Wextra", "-Wno-unused-parameter",
          "-fms-extensions"]
KERNEL32 = ["GetModuleHandleA@4", "LoadLibraryA@4", "GetProcAddress@8", "VirtualProtect@16", "GetSystemDirectoryA@8",
            "GetModuleFileNameA@12", "CreateFileA@28", "ReadFile@20", "WriteFile@20", "CloseHandle@4",
            "FlushInstructionCache@12", "GetCurrentProcess@0", "OutputDebugStringA@4", "GetFileAttributesA@4",
            "DeleteFileA@4", "VirtualAlloc@16", "SetFilePointer@16"]
EXPORTS = [("XInputGetState", 8, 2), ("XInputSetState", 8, 3), ("XInputGetCapabilities", 12, 4),
           ("XInputEnable", 4, 5), ("XInputGetDSoundAudioDeviceGuids", 12, 6),
           ("XInputGetBatteryInformation", 12, 7), ("XInputGetKeystroke", 12, 8)]


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit(f"failed: {Path(str(cmd[0])).name}")
    if r.stderr.strip():
        print(r.stderr.strip())
    return r.stdout


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "kernel32.def").write_text("LIBRARY kernel32.dll\nEXPORTS\n" + "".join(f"  {k}\n" for k in KERNEL32))
    run([BIN / "llvm-dlltool.exe", "-m", "i386", "-k", "-d", OUT / "kernel32.def", "-l", OUT / "kernel32.lib"])
    objs = []
    for src in ["hook.c", "capture.c", "census.c", "testinput.c", "options.c", "pc_strings.c", "subs.c", "pc_subs_table.c", "decensor.c", "stubs.S"]:
        obj = OUT / (Path(src).stem + ".obj")
        run([BIN / "clang.exe", *CFLAGS, "-c", ROOT / "src" / src, "-o", obj])
        objs.append(obj)
    exp = [f"/EXPORT:{n}=_{n}@{a},@{o}" for n, a, o in EXPORTS]
    run([BIN / "lld-link.exe", "/dll", "/nodefaultlib", "/entry:DllMain", "/machine:x86", "/subsystem:windows",
         "/safeseh:no", f"/out:{OUT / 'xinput1_3.dll'}", f"/map:{OUT / 'xinput1_3.map'}", *exp, *objs,
         OUT / "kernel32.lib"])
    print("built", OUT / "xinput1_3.dll", (OUT / "xinput1_3.dll").stat().st_size)


if __name__ == "__main__":
    main()
