# Change fragments

Every pull request with a change a user would notice adds one small file here, named `<PR number>.<type>.md`:

- `123.feature.md`: something new, shown under **New** in the app.
- `123.bugfix.md`: something fixed, shown under **Fixed**.
- `123.misc.md`: nothing a user would see. It is deleted at release time and never shown.

Write one or two plain sentences, for someone using the app, not for a developer. Wrapped lines are joined.

When Fastlane builds for TestFlight (`bundle exec fastlane ios share`), `scripts/collect_changes.py` folds these files into a section for that build at the top of `src/mypystub/resources/templates/changes.md`, the page the app shows under **Help → What's New**. Sections more than 30 days old (but never the newest three) move to `changes-archive.md`. Fastlane commits the result, so the build and its tag carry their own notes.

One file per change means branches never edit the same lines, so there is nothing to reorder when they merge.
