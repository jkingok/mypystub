# What's New

## 2026.11.26.1 (2026-11-26)

### New

- A folder has a Setup page like a category's: the environment variables and working folder set there apply to every script inside it, and inherited values carry the inherited icon.
- Projects made with **New** use MyPyStub's own Script view when run on their own, so their output, errors and questions look and behave as they do in MyPyStub.
- New projects come with instructions for coding agents (AGENTS.md) and a skill describing how to build an app that runs both in MyPyStub and on its own. A second skill helps a chatbot write a complete single-file script to paste into MyPyStub.
- The Logs tab has a Share button (⇪) that sends a copy of the log as a text file, for bug reports. Share now works on a Mac too (its share menu), and shows the file in its folder on other computers.

### Fixed

- On macOS, right-clicking a row in the List shows Info and Setup without also running the script or opening the folder, so Setup and Info act on the row you clicked, including `..` and the categories.
- On a small iPhone in landscape, an input() or getpass() question now sits beside its field so both stay visible above the keyboard, and the Script tab no longer keeps growing behind the keyboard.

## 2026.11.22.1 (2026-11-22)

### New

- A script's description on its Info page is now shown as Markdown (lists, `code`, links and emphasis), with the same safety as READMEs.
- Setup's **Backup** no longer freezes the app, and backs up only your Documents and settings (not installed packages or other downloads). A new **Restore** button beside it puts a backup back, keeping anything it replaces. Setup's buttons can now show icons.
- Setup's Environment list now fills the screen, inherited variables can be marked with an icon, and they're shown straight away when there are none of your own. Setup › Packages folds its list of user packages, like the other sections.
- With the Experimental Console, the window's title starts with ⏳ while a script runs and ⌨️ while it waits for you to type, and the keyboard comes up once when it starts waiting. The status row steps aside while you type.
- Each script's Setup has a **Working folder**: its own folder, a folder in the cache, or one in Documents. Swipe right on Examples or Documents to set it for everything in them. Examples now run in the cache by default, so examples that write files (such as `fancy.py`) work.
- Check for updates shows a progress bar counting through the packages it asks about, and installing a script's or project's dependencies, or Update all, counts through the downloads and installs.
- New examples: Snake Game, a classic snake game drawn on a canvas with arrow buttons, pause and a speed-up as you score; and paste_to_html, which saves the text you've copied as an HTML file.
- Check for updates now notices when Toga or toga-console, which the app takes from their git repositories, have newer commits, with a link to what changed. Before, toga-console was never checked and Toga was compared with its last PyPI release.
- Check for updates remembers its answers for the day, so checking again soon is quick and asks only about what's changed, and the Packages page shows the last results and when they were found. The wording no longer mentions TestFlight, as Android builds come from elsewhere.
- Packages you install from a git repository (name @ git+https://…) now remember the commit they came from, so Check for updates tells you when their branch has newer commits, and Update all brings them up to date.
- The result of Check for updates is a short line with emoji that fits a small phone, such as 📦 ✅ up to date · 📱 ⚠️ 4 behind, instead of running off the edge. Setup's progress row lines up its spinner, text and bar. An empty section's switch is greyed out. Arguments show just the argument, and inherited environment variables show just their value, with where they come from under ⓘ.
- Paste now works out what the text you copied is: a web page is saved as .html, Markdown as .md, JSON as .json, a notebook as .ipynb, and Python as .py as before, instead of always as a Python script. When it can't tell, it asks: end the name in .py, .html, .md or another ending to choose, or it is saved as .txt.
- Packages that PyPI offers only as source (no wheel) are now built on the device when a prototype needs them, if they are pure Python, as well as installed from wheels.

### Fixed

- Starting a script while another is still running (waiting for input, or with its own screen still up) now says "Another script is already running" and shows the Script tab, instead of running both at once and mixing up their input and output.
- Scripts that write bytes to `sys.stdout.buffer` or `sys.stderr.buffer`, read bytes from `sys.stdin.buffer` (Experimental Console), or call `sys.stdout.reconfigure()` now work in the app as they do at a terminal.
- On iPad, the tabs use the system's own tab bar again, with nothing hidden under it: List's New, New Folder and Paste row shows, and Logs and Setup no longer open blank.
- The app's own diagnostics (SafeArea's layout readings, package installs, launches and so on) no longer appear among a running script's output: everything the app logs goes to the Logs tab only. A script's own logging goes there too unless the script sets logging up itself.
- Source dependencies (a git or archive URL) install on iPhone and iPad again; building them failed on iOS with "module 'os' has no attribute 'system'".

## 2026.11.19.1 (2026-11-19)

### New

- A dependency given as a source URL (a GitHub repository or an archive) is now built with its own build backend, so projects with dynamic versions, Poetry or setup.py metadata install too.
- **New** on the List tab starts a script or a full project. A project is a Briefcase app that also builds on a computer for iOS, Android and desktop as it is; on its own it shows its output, keeps a log, and offers Restart if it stops. The Setup tab's New Project field is gone. On Android, MyPyStub's documents now appear in the Files app under a new root: if Files had MyPyStub pinned or in its recent places, that entry may stop working until you open MyPyStub from the Files app's list again. Links to individual files keep working.
- On Android, Share (scripts, projects and zipapps), Backup, About's Share and Share source code now open Android's share sheet.
- On desktop, Native mode (a Setup switch, on by default) installs dependencies with pip into one managed venv and runs each prototype in its own Python process, so it behaves as it would with the real tools. Its output, errors and input still use the Script tab.
- Dependencies can name a repository on GitHub, GitLab or Bitbucket with pip's form (`name @ git+https://github.com/owner/repo@tag`), which installs the same way on a phone (as an archive) and with pip on a computer. A repository's web page address is no longer accepted, since pip can't install it; the message gives the form to use.
- An **Experimental Console** switch in Setup (off by default) shows the Script tab in toga-console, BeeWare's console widget, from the next run: output and errors in one view, and `input()` typed straight into it.
- On iPhone, the launcher keeps its tabs and screens clear of the keyboard, including in landscape, and of the notch and home indicator.
- Setup's Environment screen no longer repeats an intro line and a foldable heading; it opens straight to the variables.
- On Android, the on-screen keyboard no longer covers the bottom of the Script tab and other screens.

### Fixed

- The contributed examples (blog_master and media_hub) now start on Android: pasting text and images uses Android's clipboard, sharing a media_hub page uses Android's share sheet, and features that are iOS-only say so instead of failing.
- The Script tab now says how a run ended, with ✅ or ❌: an error or a non-zero exit status stays on show after its message, instead of turning back into Finished.
- On Android, the keyboard now closes once a script stops asking for input, instead of staying up over the Script tab.

## 2026.11.18.1 (2026-11-18)

### Fixed

- Scripts on iOS run again. Since 2026.11.13.1 they seemed to hang with no output, only moving on when you switched tabs.
- On Android, the screen no longer stays blank when you reopen the app after Back closed it.

## 2026.11.17.2 (2026-11-17)

### New

- Paste now works on Android for copied text: it previews the text as a script and asks for a name. Copied files aren't supported yet.
- A web app's Info page shows its HTML, and the stylesheets and scripts beside it, highlighted with line numbers and folded after 300 lines, like a script's source.
- Rows in the list are named from the item's own metadata where it has one (a project's display or Briefcase app name, a zipapp's package name, a web app's name), and the window is titled with the last script's name on the Script tab and Launcher elsewhere.
- We now support building for Android with alternative Python versions. I have extended the Python packages that are included as a result to include those that _chaquopy_, which is automatically trusted by _briefcase_, offers mainly for older Python versions.
- On Android, the Back gesture and button now work in the app: they close the screen you are on (as its own Back, Cancel or Done would), return to the List tab, and go up a folder at a time, before leaving the app.
- Android releases now attach a Python 3.13 build of MyPyStub to the GitHub Release, which installs beside the main app.

### Fixed

- On Windows and Linux the list's icons are loaded as icons, so the list no longer fails with an error about a missing path.
- On the Script and Logs tabs the text fills the screen again after rotating or hiding the errors pane, and screens are laid out again when the window changes size.
- On Android, a long press on a row now opens Info and Setup without also running the script.

## 2026.11.13.1 (2026-11-13)

### New

- About shows the branch and commit of a build that isn't from main, so a test build can be told apart from a release.

### Fixed

- On Android, **Open Documents in Files** now opens your documents in the system Files browser (or the file picker), and browsing them there no longer crashes.

## 2026.11.12.1 (2026-11-12)

### New

- Check for updates now first asks GitHub whether you are running the latest build of the app. If a newer build is out you're told straight away, with a link to what's new in it; otherwise it goes on to compare Python and the bundled packages as before.
- Builds for Android are now automated, though they are functionally very incomplete.

## 2026.11.10.1 (2026-11-10)

### New

- The log is now emptied each time the app starts, so it can't keep growing in your Documents folder. If you want to keep it between launches, turn on **Preserve Logs** in Setup.
- **Clear** on the Logs tab is now **Clear Now**. It empties the log immediately, without restarting the app, after asking first. It works whether or not Preserve Logs is on.
- The Logs tab now scrolls to the newest line when it reloads, and has a **⤓** button to jump back to it from anywhere in the log. Its buttons are now quiet monochrome symbols: **↻** reloads, **⤓** goes to the newest line and **⌫** clears the log.
- About's **Source** link now opens the GitHub Release for your build, which shows what changed in it, instead of the code. Each build's What's New text is also posted on its Release.
- Pasting over a script, zipapp or project that is already there no longer asks to replace it. The new paste keeps the name, so saved settings still apply, and what it replaces is backed up in a `backups` folder beside it (a project folder is zipped). Swipe the row right for Setup and turn on Backup versions, then swipe a backup right to restore it or left to delete it. Pasting identical content changes nothing. A script's Setup screen now scrolls above its buttons, so they stay on screen, and each section (Arguments, Environment, Backup versions) folds away under its own switch.
- Static web apps: a folder with an `index.html`, or a single `.html` file, now shows in the list and opens in the app, served from the device itself (the server is adapted from Toga's positron-static). Its description and icon come from the page, its web app manifest and its favicon, like a browser would find them; Info shows the details. Back returns to the list; links to other sites open in the browser. Examples include a tip calculator.

### Fixed

- Share sheets fill the width of an iPhone again on iOS 26 and later, instead of opening as a small panel in the corner, and sharing no longer ends the app on iPad. This includes the Share button in the Media Hub example.

## 2026.11.8.1 (2026-11-08)

### New

- Paste now previews a script, project or archive as the same page that Info will show for it afterwards, instead of just the source.
- Setup has a **Share** button for a script, project or zipapp. A script or zipapp is shared as a file; a project is shared as a zip that Paste on another device unpacks as it was. Your saved arguments and variables are not sent.
- Setup now has one **Packages** page with the Python version, the packages built into the app, your user packages, aliases, and a single **Check for updates** that covers both your packages and the app's health. App health is no longer a separate page, and About no longer lists packages (the report you can share from About still does).
- Setup's Environment now lists the variables iOS already sets for the app, marked "from the system". They are hidden until you turn on **Show inherited variables** (the choice applies on every Setup screen), each row says where its value comes from before the value, and the new **ⓘ** button shows a whole value, such as a long PATH. Edit one to override it (even to blank), delete the override to bring the system's value back, or use the new ⊘ button to unset a variable so it doesn't exist at all when a script runs. The same works in each script's own Setup.
- The app now puts you back where you were after iOS ends it in the background: the same tab, the folder you were browsing, the Setup page that was open, and the Help page showing. If a script was running you are asked whether to run it again. It does nothing after an update, and you can turn it off with **Resume where I left off** in Setup. A new example, `basics/resume_counter.py`, shows how a script can do the same.

### Fixed

- On iPhone, choosing the Logs tab shows the logs straight away, instead of an empty page until you press Reload.

## 2026.11.6.1 (2026-11-06)

### New

- A script can now depend on a wheel at a web address, for example `foo @ https://example.com/foo-1.0-py3-none-any.whl`, optionally with `#sha256=` to check the file.
- A script can now depend on a pure-Python project from a GitHub address or a source archive, for example `toga-console @ https://github.com/beeware/toga-console`. Anything that needs compiling is refused with a reason, as is any wheel that isn't pure Python.
- Setup has a new "Open Documents in Files" button, which opens your Documents folder in the Files app.

### Fixed

- Fixed a script not running after an example such as Blog Master had been run: the launcher lost its own settings. Errors that used to appear only in the Log now show in a dialog. Pasted scripts are offered the name they were copied with and always saved as .py, and a pasted name never ends in a repeated extension such as .py.py. Copied text named notes.txt is saved as notes.py, and a plain text file can't be imported.
- Fixed the Media Hub example failing on its first run: its default settings were missing.
- A dependency that points at a URL or a git repository is now refused with an explanation, instead of installing a different package of the same name from PyPI.

## 2026.11.4.2 (2026-11-04)

### New

- A **New Folder** button sits beside **Paste** above the list, on its left. It makes a folder in the folder you are browsing. Both buttons are greyed out where nothing can be added: at the top, in the examples, and inside a project or zipapp. Empty folders show 🪣 Empty.
- Adding or editing an argument, a variable, or a pasted file name now asks in a small alert over the current screen instead of taking over the whole screen.
- Swipe right on a script or project and choose **Make Quick Start** to have the app offer to run it each time it opens. You're always asked first, and you can change or clear the choice from the Setup tab's **Clear Quick Start**.
- Paste now previews what it will add — a script's source, a file's or zipapp's details, or an archive's contents — with **Cancel** and **Import** at the top, so you can see what you're importing before it lands. You're still asked for a file name only when one is needed.
- The About page now has a **Share source code** button that shares a zip of the app's own Python code, exactly as it runs on your device. It's a way to read or check the running source yourself, without having to trust the Source link above it.
- Examples now include `claude/` and `joshua/`, two folders of extra scripts and apps to explore.

### Fixed

- The Paste button no longer shows as "P...te" on some iPhones: the buttons above the list now share the width.
- The Setup menu fills the screen the first time you open it, instead of staying narrow and to the left.
- Following a security review, a `patch_app.py` file in your MyPyStub folder is no longer run automatically at launch. It now appears in the list and runs like any other script, so no file can take over the app before you tap it.
- **Paste** now works with a file copied in the Files app, which used to say there was nothing to paste. If you copy a folder, or don't allow pasting, it tells you what to do.

## 2026.11.3.2 (2026-11-03)

### New

- The Help tab has a What's New page, which opens the first time you start a new version.
- The About page has a Source link to the code for the version you're running, and web links there open in your browser.
