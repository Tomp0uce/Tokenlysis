class StaticFiles:
    def __init__(self, directory: str | None = None, html: bool = False):
        self.directory = directory
        self.html = html
