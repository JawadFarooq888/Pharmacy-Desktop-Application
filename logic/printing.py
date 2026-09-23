"""Send a file straight to the default printer, no manual "open then print"
step for the cashier. Uses Windows' own shell print verb, which hands the
file to whatever's registered to open PDFs (Edge, Adobe Reader, etc.) and
tells it to print -- reliable and needs no extra dependency."""
import os
import sys


def print_document(path) -> bool:
    """Best-effort direct print. Returns True if the OS accepted the
    request (not a guarantee ink hit paper -- that's between the OS and the
    printer). Never raises: callers should treat a False return as "the
    user may need to print manually" rather than fail the whole operation."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path), "print")
            return True
        return False
    except Exception:
        return False
