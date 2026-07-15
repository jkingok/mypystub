import asyncio
import builtins
import importlib
import io
import os
from pathlib import Path
import re
import threading
import toga
from toga.style import Pack

# Regex pattern to match standard ANSI escape sequences (like \x1b[31m)
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

def clean_ansi(text: str) -> str:
    """Removes ANSI color and formatting codes from a string."""
    return ANSI_ESCAPE_RE.sub("", text)

class TogaStream(io.TextIOBase):
    def __init__(self, on_write_callback, wait_for_flush=False):
        """on_write_callback is a function that accepts a string

        and updates the Toga GUI safely.
        """
        self.pending = ""
        self.on_write_callback = on_write_callback
        self.wait_for_flush = wait_for_flush

    def write(self, s):
        s = clean_ansi(s)
        if s:  # Avoid empty writes
            if self.wait_for_flush:
                self.pending += s
            else:
                self.on_write_callback(s)
        return len(s)

    def flush(self):
        # Builtin print occasionally calls flush(); we can treat it as a no-op
        # or use it as a way to ensure we don't overload the threading crosstalk
        if self.pending:
            self.on_write_callback(self.pending)
            self.pending = "" 

class ScriptRunner:
    def __init__(self, app, input_label, input_field, toggle_input):
        self.app = app
        self.input_label = input_label
        self.input_field = input_field
        #self.print_field = app.widgets["print_text"]
        #self.scroll = scroll
        self.toggle_input = toggle_input
        self.input_field.on_confirm = self.handle_ui_submit
        # Sync primitives
        self._input_event = threading.Event()
        self._input_value = ""

        # Keep track of original builtins
        self._original_print = builtins.print
        self._original_input = builtins.input

        self.stream = TogaStream(self.append_to_log)
        
    def hook_builtins(self):
        """Intercept print and input."""
        builtins.print = self._custom_print
        builtins.input = self._custom_input

    def unhook_builtins(self):
        """Restore default terminal behavior."""
        builtins.print = self._original_print
        builtins.input = self._original_input

    async def _auto_scroll_loop(self):
        """A persistent timer loop that checks for updates every 1s."""
        while True:
            try:
                if True:
                    # 1. Clear the flag immediately
                    #self.pending_scroll = False

                    # 2. Force Toga to calculate the new text bounds
                    #self.text_widget.refresh()

                    # 3. Give the native layout engine one frame to update coordinates
                    #await asyncio.sleep(0.01)

                    # 4. Snap to the true bottom
                    self.scroll.vertical_position = (
                        self.scroll.max_vertical_position
                    )

                # Tick rate: Check 10 times a second (100ms interval)
                await asyncio.sleep(1)

            except Exception as e:
                # Defensive error handling to ensure an unexpected layout glitch
                # doesn't crash the entire background timer task
                print(f"Scroll timer error: {e}")

    def mainthread_append_to_log(self, message: str) -> None:
        if (w := self.app.widgets["print_text"]):
            w.value += f"{message}"
            #self.print_field.refresh()
            #await asyncio.sleep(0.01)
            #self.scroll.vertical_position = self.scroll.max_vertical_position
        elif self._original_print:
            self._original_print(message) 

    def append_to_log(self, message: str) -> None:
        """
        Safely appends a message to the UI log view.
        The @ui.main_thread decorator guarantees this executes safely on 
        the main thread, even when called from a background thread.
        """
        self.app.loop.call_soon(lambda: self.mainthread_append_to_log(message))
        #asyncio.create_task(self.mainthread_append_to_log(message))

    def _custom_print(self, *args, **kwargs):
        """Generic print wrapper that hijacks the 'file' target."""
        # Check if the student explicitly passed a file argument
        target_file = kwargs.get("file", None)

        # If they didn't specify a file, or they specified standard output,
        # redirect it to our custom Toga stream handler.
        #if target_file is None or target_file in (sys.stdout, sys.__stdout__):
        kwargs["file"] = self.stream

        # Pass everything (positionals, sep, end, flush, and our modified file)
        # down to the native builtin print logic.
        self._original_print(*args, **kwargs)

    def _custom_input(self, prompt=""):
        # 1. Clear any old event state
        self._input_event.clear()
        self._input_value = ""

        # 2. Update and show UI on the main thread
        def setup_ui():
            self.toggle_input(True)
            if prompt:
                self.input_label.text = prompt
            
            self.input_field.value = ""
            self.input_field.focus()

        toga.App.app.loop.call_soon(setup_ui)

        # 3. Block the student's background thread until the event is set
        self._input_event.wait()

        # 4. Return the captured value back to the student's script
        return self._input_value

    def handle_ui_submit(self, widget):
        """Triggered by the Toga TextInput's on_confirm handler."""
        # Capture the text
        self._input_value = self.input_field.value

        self.toggle_input(False)

        # Release the background thread's lock
        self._input_event.set()

    def run_student_script(self, script_func):
        """Executes the target script function in a background thread."""
        # Start the persistent background timer loop
        #self._auto_scroll = asyncio.create_task(self._auto_scroll_loop())
        def worker():
            print("In worker...")
            self.hook_builtins()
            try:
                script_func()
            finally:
                self.unhook_builtins()
                print("Back out of worker")
        thread = threading.Thread(target=worker, daemon=True)
        print("About to start worker...")
        thread.start()

class Prototype:
    def __init__(self, host_app, on_done):
        self.app = host_app
        self.on_done_callback = on_done  # This is your ticket back to safety
        self.title = "Script Bridge"
    
    def start(self, fp):
        print("Starting...")
        def script(file_path):
            # Dynamically load the python module from an arbitrary path
            module_name =  file_path.parent.name
            spec = importlib.util.spec_from_file_location(module_name, file_path, submodule_search_locations=(file_path.parent,))
            module = importlib.util.module_from_spec(spec)
            
            # Execute the module code so classes are defined
            spec.loader.exec_module(module)
        self.script_runner.run_student_script(lambda fp=fp: script(fp))

    def get_content(self):
        layout = toga.Column()
        
        keyboard_box = toga.Box(style=Pack(flex=1, visibility="hidden"))
        def pad_keyboard(on):
            #keyboard_box.style.visibility = "visible" if on else "hidden"
            keyboard_box.style.flex = 1 if on else 0
        prompt_lbl = toga.Label("Input") 
        input_txt = toga.TextInput(style=Pack(flex=1), on_gain_focus=lambda m: pad_keyboard(True), on_lose_focus=lambda m: pad_keyboard(False))
        
        input_box = toga.Column(
            children=[
                prompt_lbl,
                input_txt
            ],
            text_align="center")
        def toggle_input(on):
            if on:
                layout.insert(0, input_box)
            else:
                layout.remove(input_box)
            pad_keyboard(on)
        self.print_text = toga.MultilineTextInput(value="", readonly=True) #, style=Pack(flex=1))
        scroll_box = toga.ScrollContainer(horizontal=False, content=self.print_text, style=Pack(flex=1))
        layout.add(scroll_box)
        layout.add(keyboard_box)
        layout.add(toga.Button("◀ Back", on_press=self.exit_back))
        
        self.script_runner = ScriptRunner(self.app, prompt_lbl, input_txt, self.print_text, scroll_box, toggle_input)
        file_path = Path("~/Documents/scripts/apply_my_template.py").expanduser()
        print(f"Launching from path: {file_path}")
        self.app.loop.call_soon(lambda s=file_path: self.start(s))
        
        return layout

    def exit_back(self, button):
        # Fire the parent's handler cleanly
        self.on_done_callback()