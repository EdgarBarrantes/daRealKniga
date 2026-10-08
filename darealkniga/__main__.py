from .cli import main

# guarded: on Windows and macOS, worker processes re-import this module
if __name__ == "__main__":
    main()
