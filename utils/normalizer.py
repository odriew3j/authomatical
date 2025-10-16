# utils/normalizer.py
import re

# Mapping Persian and Arabic numbers to English
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"

digit_map = {p: e for p, e in zip(PERSIAN_DIGITS, ENGLISH_DIGITS)}
digit_map.update({a: e for a, e in zip(ARABIC_DIGITS, ENGLISH_DIGITS)})

def normalize_digits(text: str) -> str:
    """ Convert Persian/Arabic numbers to English """
    if not isinstance(text, str):
        text = str(text)
    return "".join(digit_map.get(ch, ch) for ch in text)

def normalize_price(value: str) -> int:
    """ Price clearing and conversion to English integer """
    value = normalize_digits(value)
    # remove str,...
    value = re.sub(r"[^\d]", "", value)
    return int(value) if value else 0
