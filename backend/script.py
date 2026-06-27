"""Script helpers — turning a pasted block of text into the list of lines the
brain will restyle. Kept tiny and pure so it's easy to test and reason about."""


def split_lines(block: str) -> list[str]:
    """Split a pasted script into clean lines: one per line break, trimmed, with
    blank / whitespace-only lines dropped. (CRLF and CR endings are handled.)"""
    return [line.strip() for line in block.splitlines() if line.strip()]
