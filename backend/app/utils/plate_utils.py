import itertools
import re

# e.g. GJ01AB1234 (state, district, 0-3 series letters, 4 digits)
PLATE_PATTERN = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$")

# look-alike characters, used only where the plate format allows just one kind
TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "T": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}

# characters OCR commonly mixes up (used to look for alternative readings of a plate)
CONFUSABLE = {
    "O": "0Q", "0": "OD", "I": "1L", "1": "IL", "B": "8", "8": "B", "S": "5", "5": "S",
    "Z": "2", "2": "Z", "G": "6", "6": "G", "D": "0", "Q": "0", "L": "1",
}


def normalize_plate(text: str | None) -> str:
    """Upper-case the text and drop spaces, hyphens and other symbols.

    Letters and digits are never swapped here (no O -> 0 guessing).
    """
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def looks_like_plate(text: str | None) -> bool:
    return bool(PLATE_PATTERN.match(normalize_plate(text)))


def canonical_plate(text: str | None) -> str:
    """Normalised plate with a one-digit district padded to two digits (GJ1AB1234 -> GJ01AB1234)."""
    t = normalize_plate(text)
    match = re.match(r"^([A-Z]{2})(\d)([A-Z]{1,3}\d{4})$", t)
    if match:
        return f"{match.group(1)}0{match.group(2)}{match.group(3)}"
    return t


def plate_variants(text: str | None) -> list[str]:
    """Spellings of the SAME registration that may be stored in the database.

    GJ01AB1234, GJ1AB1234 and 'gj 01 ab-1234' all describe one vehicle. No characters are guessed here.
    """
    plain = normalize_plate(text)
    if not plain:
        return []
    variants = [plain, canonical_plate(plain)]
    match = re.match(r"^([A-Z]{2})0(\d[A-Z]{1,3}\d{4})$", plain)
    if match:
        variants.append(match.group(1) + match.group(2))
    seen, ordered = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


def strip_noise(text: str | None) -> str:
    """Remove text that often sits on plates but is not part of the number (e.g. the 'IND' mark)."""
    t = normalize_plate(text)
    if t.startswith("IND") and len(t) >= 11:
        t = t[3:]
    return t


def fix_indian_plate(text: str | None) -> str:
    """Fix look-alike characters using the position rules of an Indian plate.

    State code (2 letters), district (2 digits), series (letters), number (4 digits).
    Only applied when the length fits (8-11 characters); otherwise the text is returned unchanged,
    so one registration number is never silently turned into a different one by guesswork.
    """
    t = strip_noise(text)
    if not 8 <= len(t) <= 11:
        return t
    head, district, series, number = t[:2], t[2:4], t[4:-4], t[-4:]
    head = "".join(TO_LETTER.get(c, c) for c in head)
    district = "".join(TO_DIGIT.get(c, c) for c in district)
    series = "".join(TO_LETTER.get(c, c) for c in series)
    number = "".join(TO_DIGIT.get(c, c) for c in number)
    return head + district + series + number


def ocr_alternatives(text: str | None, max_changes: int = 2, limit: int = 80) -> list[str]:
    """Other plausible spellings of an OCR reading (look-alike swaps), valid-looking plates only.

    Used ONLY to search records that already exist (never to invent a plate), and the caller
    must accept a result only when exactly one of these alternatives matches a real record.
    """
    base = normalize_plate(text)
    if len(base) < 8:
        return []
    positions = [i for i, c in enumerate(base) if c in CONFUSABLE]
    found: list[str] = []
    for changes in range(1, max_changes + 1):
        for chosen in itertools.combinations(positions, changes):
            options = [CONFUSABLE[base[i]] for i in chosen]
            for replacement in itertools.product(*options):
                chars = list(base)
                for index, char in zip(chosen, replacement):
                    chars[index] = char
                candidate = "".join(chars)
                if candidate != base and PLATE_PATTERN.match(candidate) and candidate not in found:
                    found.append(candidate)
                    if len(found) >= limit:
                        return found
    return found