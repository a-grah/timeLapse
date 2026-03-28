try:
    from importlib.metadata import version
    __version__ = version("timelapse")
except Exception:
    __version__ = "dev"  # fallback when not installed as a package
