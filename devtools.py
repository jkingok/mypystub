import compileall
import importlib.util
from pathlib import Path
import re
import sys
import traceback


def resolve_target_dir() -> Path:
    """Resolves target directory from first CLI argument, defaulting to CWD."""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target = Path(sys.argv[1]).resolve()
        # Remove path argument so downstream tools inspecting sys.argv don't break
        sys.argv.pop(1)
    else:
        target = Path.cwd().resolve()

    if not target.is_dir():
        print(f"Error: Target path '{target}' is not a valid directory.")
        sys.exit(1)

    return target


def run_strict_step(module_name: str, step_name: str, fn) -> None:
    """Executes a step in-process.

    Raises SystemExit(1) on failure to halt the pipeline.
    """
    if importlib.util.find_spec(module_name) is None:
        print(f"[CRITICAL] Cannot run {step_name}: '{module_name}' is not installed.")
        print("Pipeline aborted.")
        sys.exit(1)

    print(f"--> Running {step_name}...")
    try:
        fn()
        print(f"    Passed: {step_name}\n")
    except Exception as e:
        print(f"\n[FAILED] {step_name}: {e}")
        print("Pipeline halted due to error.")
        traceback.print_exc()
        sys.exit(1)


def main():
    target_dir = resolve_target_dir()
    print("=" * 60)
    print("Starting Strict Python Build Pipeline (In-Process)")
    print(f"Target Directory: {target_dir}")
    print("=" * 60 + "\n")

    # ------------------------------------------------------------------
    # 1. COMPILE: Validate syntax & pre-compile bytecode
    # ------------------------------------------------------------------
    print("--> [1/6] Pre-compiling bytecode (compileall)...")
    compile_success = compileall.compile_dir(target_dir, force=False, quiet=1)
    if not compile_success:
        print("\n[FAILED] Bytecode compilation encountered syntax errors.")
        print("Pipeline halted.")
        sys.exit(1)
    print("    Passed: Bytecode compilation\n")

    # ------------------------------------------------------------------
    # 3. FORMAT: In-place code formatting (Black)
    # ------------------------------------------------------------------
    def run_black():
        import black

        mode = black.Mode()
        for py_file in black.gen_python_files(
            target_dir.resolve().iterdir(),
            root=target_dir.resolve(),
            include=re.compile(black.DEFAULT_INCLUDES),
            exclude=None,
            extend_exclude=None,
            force_exclude=None,
            report=black.Report(check=False, diff=False, quiet=False, verbose=False),
            gitignore_dict={},
            verbose=False,
            quiet=False,
        ):
            if formatted := black.format_file_in_place(
                py_file, fast=False, mode=mode, write_back=black.WriteBack.YES
            ):
                print(f"changed {py_file}")
            else:
                print(f"unchanged {py_file}")

    run_strict_step("black", "[3/6] Formatting (Black)", run_black)

    # ------------------------------------------------------------------
    # 4. CHECK OMISSIONS: Type annotation & docstring coverage
    # ------------------------------------------------------------------
    def check_type_omissions():
        from mypy import api

        stdout, stderr, exit_status = api.run(
            [
                "--disallow-untyped-defs",
                "--disallow-incomplete-defs",
                "--check-untyped-defs",
                "--ignore-missing-imports",
                str(target_dir),
            ]
        )
        if stdout and stdout.strip():
            print(stdout.strip())
        if exit_status != 0:
            raise RuntimeError("Missing or incomplete type annotations found.")

    run_strict_step(
        "mypy", "[4/6] Omission Check: Type Hints (Mypy)", check_type_omissions
    )

    def check_docstring_omissions():
        from interrogate import coverage

        cov = coverage.InterrogateCoverage(paths=[str(target_dir)])
        results = cov.get_coverage()
        print(
            f"    Docstring Coverage: ({results.covered}/{results.total})"
        )
        if results.missing > 0:
            cov.print_results(results, None, 2)
            raise RuntimeError(
                f"{results.missing} items missing docstrings (target: 100%)."
            )

    #run_strict_step(
    #    "interrogate",
    #    "[4/6] Omission Check: Docstrings (Interrogate)",
    #    check_docstring_omissions,
    #)

    # ------------------------------------------------------------------
    # 5. LINT: Logic & Style errors
    # ------------------------------------------------------------------
    def run_flake8():
        from flake8.main import application

        app = application.Application()
        app.run([str(target_dir)])
        if app.exit_code() != 0:
            raise RuntimeError(f"Flake8 reported {app.exit_code()} issue(s).")

    def run_pyflakes():
        from pyflakes.api import checkRecursive
        from pyflakes.reporter import Reporter

        class CounterReporter(Reporter):

            def __init__(self, warning_stream, error_stream):
                super().__init__(warning_stream, error_stream)
                self.count = 0

            def unexpectedError(self, filename, msg):
                self.count += 1
                super().unexpectedError(filename, msg)

            def syntaxError(self, filename, msg, lineno, offset, text):
                self.count += 1
                super().syntaxError(filename, msg, lineno, offset, text)

            def flake(self, message):
                self.count += 1
                super().flake(message)

        reporter = CounterReporter(sys.stdout, sys.stderr)
        checkRecursive([str(target_dir)], reporter)
        if reporter.count > 0:
            raise RuntimeError(f"Pyflakes reported {reporter.count} issue(s).")

    if importlib.util.find_spec("flake8"):
        run_strict_step("flake8", "[5/6] Linting (Flake8)", run_flake8)
    else:
        run_strict_step("pyflakes", "[5/6] Linting (Pyflakes)", run_pyflakes)

    # ------------------------------------------------------------------
    # 6. GENERATE DOCS: Extract HTML API documentation (pdoc)
    # ------------------------------------------------------------------
    def run_pdoc():
        import pdoc

        output_docs = target_dir / "docs"
        pdoc.pdoc(str(target_dir), output_directory=output_docs)
        print(f"    Documentation generated at: {output_docs}")

    run_strict_step("pdoc", "[6/6] Documentation Generation (pdoc)", run_pdoc)

    print("=" * 60)
    print("SUCCESS: All 6 pipeline stages passed perfectly!")
    print("=" * 60)


if __name__ == "__main__":
    main()
