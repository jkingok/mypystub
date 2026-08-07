import compileall
import importlib.util
import re
import sys
import traceback
from pathlib import Path


def run_in_process(module_name: str, task_name: str, fn) -> bool:
    """Executes a function if the module is installed in the iOS Python environment."""
    if importlib.util.find_spec(module_name) is None:
        print(f"--> Skipping {task_name}: '{module_name}' is not installed.")
        return False

    print(f"--> Running {task_name}...")
    try:
        fn()
        print(f"    Success: {task_name}")
        return True
    except Exception as e:
        print(f"    Failed: {task_name} ({e})")
        traceback.print_exc()
        return False


def main():
    print("Starting In-Process Python Build Pipeline (iOS Safe)\n")

    # 1. Bytecode Compilation (Standard Lib - Always Works)
    print("--> Pre-compiling bytecode...")
    success = compileall.compile_dir(".", force=False, quiet=1)
    print(f"    Bytecode compilation: {'Passed' if success else 'Failed'}\n")

    # 2. In-Process Formatting (Black)
    def run_black():
        import black

        mode=black.Mode()
        for py_file in black.gen_python_files(
            Path(".").resolve().iterdir(), 
            root=Path(".").resolve(),
            include=re.compile(black.DEFAULT_INCLUDES),
            exclude=None,
            extend_exclude=None,
            force_exclude=None,
            report=black.Report(check=False, diff=False, quiet=False, verbose=False),
            gitignore_dict={},
            verbose=False,
            quiet=False
        ):
            if formatted := black.format_file_in_place(
                py_file, fast=False, mode=mode,  write_back=black.WriteBack.YES
            ):
                print(f"changed {py_file}")
            else:
                print(f"unchanged {py_file}")
            

    run_in_process("black", "Black Formatting", run_black)

    # 3. In-Process Linting (Pyflakes - Pure Python substitute for Ruff)
    def run_pyflakes():
        from pyflakes.api import checkRecursive
        from pyflakes.reporter import Reporter

        reporter = Reporter(sys.stdout, sys.stderr)
        checkRecursive(["."], reporter)

    run_in_process("pyflakes", "Pyflakes Linting", run_pyflakes)

if __name__ == "__main__":
    main()
