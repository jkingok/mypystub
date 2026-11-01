"""Entry point: greet the user from inside the package."""

from hello_project.greeting import greet


def main() -> None:
    """Print a greeting."""
    print(greet("from a project folder", 1_234_567))


if __name__ == "__main__":
    main()
