try:
    from .paircoder_module import main
except ImportError:
    from paircoder_module import main


if __name__ == "__main__":
    main()
