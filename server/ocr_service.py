import os
import re
from collections import Counter

import certifi
import cv2
import easyocr


os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

_reader = None

PROVINCE_CHARS = "京津沪渝冀豫云辽黑湘皖鲁苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼新"


def get_reader():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
    return _reader


def clean_text(text: str) -> str:
    text = text.strip().upper()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^A-Z0-9\u4e00-\u9fff]", "", text)
    return text


def fix_city_code(text: str) -> str:
    text = clean_text(text)
    if len(text) < 2:
        return text

    if text[0] not in PROVINCE_CHARS:
        return text

    city_map = {
        "4": "A",
        "8": "B",
        "1": "I",
    }

    second = city_map.get(text[1], text[1])
    return text[0] + second + text[2:]

def extract_prefix(text: str) -> str:
    text = clean_text(text)

    if len(text) < 2:
        return ""

    text = fix_city_code(text)

    prefix = text[:2]
    if is_prefix(prefix):
        return prefix

    return ""



def is_prefix(text: str) -> bool:
    text = clean_text(text)
    if len(text) != 2:
        return False
    if text[0] not in PROVINCE_CHARS:
        return False
    if not text[1].isalpha() or text[1] in {"I", "O"}:
        return False
    return True


def is_suffix_strict(text: str) -> bool:
    text = clean_text(text)

    if len(text) !=5:
        return False

    for ch in text:
        if ch in {"I", "O"}:
            return False
        if not (ch.isdigit() or ("A" <= ch <= "Z")):
            return False

    return True



def is_possible_plate(text: str) -> bool:
    text = clean_text(text)

    if len(text) not in (7, 8):
        return False

    if text[0] not in PROVINCE_CHARS:
        return False

    if not text[1].isalpha() or text[1] in {"I", "O"}:
        return False

    if len(text) == 7:
        suffix = text[2:]
        return all((ch.isdigit() or ch.isalpha()) and ch not in {"I", "O"} for ch in suffix)

    if text[2] not in {"D", "F"}:
        return False

    suffix = text[3:]
    return all((ch.isdigit() or ch.isalpha()) and ch not in {"I", "O"} for ch in suffix)


def split_plate_regions(image):
    h, w = image.shape[:2]

    # 左边给省简称+城市代码多留一点空间
    left = image[:, : int(w * 0.42)]

    # 右边保留重叠区域，避免把边界字符切掉
    right = image[:, int(w * 0.25):]

    return left, right


def expand_suffix_candidates(text: str):
    text = clean_text(text)

    confusion_map = {
        "0": ["0", "Q"],
        "1": ["1", "M"],
        "2": ["2", "Z"],
        "5": ["5", "S"],
        "8": ["8", "B"],
        "6": ["6", "G"],
    }

    results = [""]

    for ch in text:
        choices = confusion_map.get(ch, [ch])
        new_results = []
        for prefix in results:
            for choice in choices:
                new_results.append(prefix + choice)
        results = new_results

        if len(results) > 100:
            results = results[:100]

    return results


def score_suffix(text: str) -> int:
    text = clean_text(text)
    score = 0

    if len(text) == 5:
        score += 5

    has_digit = any(ch.isdigit() for ch in text)
    has_alpha = any(("A" <= ch <= "Z") for ch in text)

    if has_digit:
        score += 2
    if has_alpha:
        score += 4
    if has_digit and has_alpha:
        score += 15

    # 全数字强烈降权
    if text.isdigit():
        score -= 25

    return score



def read_texts(reader, image):
    results = reader.readtext(
        image,
        detail=0,
        paragraph=False,
        width_ths=0.5,
        decoder="greedy"
    )
    return [clean_text(x) for x in results if clean_text(x)]


def recognize_by_segments(image_path: str):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("图片读取失败")

    # 固定尺寸，降低几何差异
    image = cv2.resize(image, (440, 140))
    left_img, right_img = split_plate_regions(image)

    reader = get_reader()

    prefix_candidates = []
    suffix_candidates = []

    # 左侧：前缀
    left_gray = cv2.cvtColor(left_img, cv2.COLOR_BGR2GRAY)
    left_variants = [
        left_img,
        left_gray,
    ]

    # 右侧：后缀
    right_gray = cv2.cvtColor(right_img, cv2.COLOR_BGR2GRAY)
    right_variants = [
        right_img,
        right_gray,
        cv2.bilateralFilter(right_gray, 9, 75, 75),
    ]

    for variant in left_variants:
        results = read_texts(reader, variant)
        print("Prefix raw results:", results)
        for item in results:
            prefix = extract_prefix(item)
            if prefix:
                prefix_candidates.append(prefix)


    for variant in right_variants:
        results = read_texts(reader, variant)
        print("Suffix raw results:", results)
        for item in results:
            suffix_candidates.append(item)

    print("Prefix candidates:", prefix_candidates)
    print("Suffix candidates:", suffix_candidates)

    if not prefix_candidates or not suffix_candidates:
        raise ValueError("OCR分段识别失败，请重新拍摄")

    prefix = Counter(prefix_candidates).most_common(1)[0][0]

    expanded_suffixes = []
    for suffix in suffix_candidates:
        expanded_suffixes.append(suffix)

        # 6位时尝试去掉首位或末位，处理多识别一位的情况
        if len(suffix) == 6:
            expanded_suffixes.append(suffix[1:])
            expanded_suffixes.append(suffix[:-1])

        expanded_suffixes.extend(expand_suffix_candidates(suffix))

    valid_suffixes = []
    for item in expanded_suffixes:
        ok = is_suffix_strict(item)
        print("Check suffix:", item, "=>", ok)
        if ok:
            valid_suffixes.append(item)


    print("Expanded suffixes:", expanded_suffixes)
    print("Valid suffixes:", valid_suffixes)

    if not valid_suffixes:
        raise ValueError("后缀识别失败，请重新拍摄")

    suffix_counter = Counter(valid_suffixes)
    unique_suffixes = list(suffix_counter.keys())

    unique_suffixes.sort(
        key=lambda x: (
            score_suffix(x),
            suffix_counter[x],
        ),
        reverse=True
    )


    print("Suffix counter:", suffix_counter)
    print("Ranked suffixes:", unique_suffixes)

    suffix = unique_suffixes[0]
    plate = prefix + suffix

    if is_possible_plate(plate):
        return plate

    raise ValueError("OCR分段识别后仍未得到有效车牌")


def recognize_plate(image_path: str) -> str:
    return recognize_by_segments(image_path)
