# Interpreter and platform report, standard library only.
import locale
import os
import platform
import struct
import sys

print("=== Interpreter ===")
print("Version:", sys.version)
print("Version info:", tuple(sys.version_info)[:3])
print("Implementation:", platform.python_implementation())
print("Executable:", sys.executable)
print("Prefix:", sys.prefix)
print("Base prefix:", sys.base_prefix)
print("Pointer size (bits):", struct.calcsize("P") * 8)
print("Byte order:", sys.byteorder)
print("Max int size:", sys.maxsize)
print("Float max:", sys.float_info.max)
print("Recursion limit:", sys.getrecursionlimit())
print("Default encoding:", sys.getdefaultencoding())
print("File system encoding:", sys.getfilesystemencoding())
print("Locale:", locale.getpreferredencoding(False))

print()
print("=== Platform ===")
print("System:", platform.system())
print("Release:", platform.release())
print("Version:", platform.version())
print("Machine:", platform.machine())
print("Processor:", platform.processor())
print("Node name:", platform.node())
print("Architecture:", platform.architecture())
print("Uname:", platform.uname())
print("Libc:", platform.libc_ver())

print()
print("=== Process and environment ===")
print("PID:", os.getpid())
print("Parent PID:", os.getppid())
print("Working dir:", os.getcwd())
print("User home:", os.path.expanduser("~"))
print("CPU count:", os.cpu_count())
print("Path separator:", os.sep)
print("Line separator repr:", repr(os.linesep))
print("PATH entries:", len(os.environ.get("PATH", "").split(os.pathsep)))
print("Env var count:", len(os.environ))
print("Env keys (first 15):")
for key in sorted(os.environ)[:15]:
    print(" ", key)
