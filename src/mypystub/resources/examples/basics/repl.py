"""A tiny read-eval-print loop: type Python, see the result; exit() to stop."""


def main() -> None:
    """Read a line, evaluate it, print the result, and loop.

    One dictionary holds the variables, so `x = 6` then `x * 7` gives 42.
    Expressions are evaluated and their result printed; anything else, such
    as an assignment or an import, is run as a statement. It takes one line
    at a time, so there are no multi-line blocks: the standard library's
    `code.interact()` is the full version, and it works here too.
    """
    namespace: dict[str, object] = {"__name__": "__repl__"}
    print("Type Python. exit() ends the loop.")
    while True:
        line = input(">>> ")
        if not line.strip():
            continue
        try:
            try:
                result = eval(line, namespace)  # an expression
            except SyntaxError:
                exec(line, namespace)  # noqa: S102 (a statement: a REPL runs what you type)
            else:
                if result is not None:
                    print(repr(result))
        except Exception as error:  # noqa: BLE001 (show it and carry on)
            print(f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
