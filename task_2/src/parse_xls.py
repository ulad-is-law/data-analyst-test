import re
from pathlib import Path
import fitz  # PyMuPDF
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

FILES_SPEC = [
    # (год1, год2, направление, формат_с_весом_нетто, имя_файла)
    (2008, 2009, "export", False, "2008-2009_Экспорт_Раздел2.pdf"),
    (2008, 2009, "import", False, "2008-2009_Импорт_Раздел2.pdf"),
    (2010, 2011, "export", False, "2010-2011_Экспорт_Раздел2.pdf"),
    (2010, 2011, "import", False, "2010-2011_Импорт_Раздел2.pdf"),
    (2012, 2013, "export", True,  "2012-2013_Экспорт_Раздел2.pdf"),
    (2012, 2013, "import", True,  "2012-2013_Импорт_Раздел2.pdf"),
    (2013, 2014, "export", False, "2013-2014_Экспорт_Раздел2.pdf"),
    (2013, 2014, "import", False, "2013-2014_Импорт_Раздел2.pdf"),
    (2015, 2016, "export", False, "2015-2016_Экспорт_Раздел2.pdf"),
    (2015, 2016, "import", False, "2015-2016_Импорт_Раздел2.pdf"),
    (2017, 2018, "export", False, "2017-2018_Экспорт_Раздел2.xls"),
    (2017, 2018, "import", False, "2017-2018_Импорт_Раздел2.xls"),
    (2019, 2020, "export", False, "2019-2020_Экспорт_Раздел2.xls"),
    (2019, 2020, "import", False, "2019-2020_Импорт_Раздел2.xls"),
    (2020, 2021, "export", False, "2020-2021_Экспорт_Раздел2.xls"),
    (2020, 2021, "import", False, "2020-2021_Импорт_Раздел2.xls"),
]


def to_float(val) -> float:
    s = str(val).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if s in ("", "-", "nan", "None"):
        return 0.0
    return float(s)


def merge_cells_in_rotated_row(words, gap_threshold=8.0):
    """Склеивает разряды одного числа (например '19' и '439' -> '19439') по зазору между словами."""
    words = sorted(words, key=lambda w: -w[3])  # слева направо на повёрнутой на 90° странице
    cells = []
    cur_text = words[0][4]
    cur_end = words[0][1]

    for w in words[1:]:
        gap = cur_end - w[3]
        if gap <= gap_threshold:
            cur_text += " " + w[4]
        else:
            cells.append(cur_text.strip())
            cur_text = w[4]
        cur_end = w[1]
    cells.append(cur_text.strip())
    return cells


def parse_pdf_080711(filepath: Path, has_net_weight: bool):
    doc = fitz.open(filepath)
    target_row_words = None

    for page in doc:
        if "080711" not in page.get_text("text"):
            continue
        words = page.get_text("words")
        words.sort(key=lambda w: (w[0], -w[1]))

        rows = []
        cur = [words[0]]
        cur_x = words[0][0]
        for w in words[1:]:
            if abs(w[0] - cur_x) <= 4.0:
                cur.append(w)
            else:
                rows.append(cur)
                cur = [w]
                cur_x = w[0]
        rows.append(cur)

        for idx, r in enumerate(rows):
            row_txt = " ".join(w[4] for w in r)
            if re.search(r"\b080711\b", row_txt):
                # Если строка разорвана на 2 (единица измерения на следующей строке), берём следующую
                if not re.search(r"\b(тонн|кг|т)\b", row_txt) and idx + 1 < len(rows):
                    target_row_words = rows[idx + 1]
                else:
                    target_row_words = r
                break
        if target_row_words is not None:
            break
    doc.close()

    # Если кода 080711 нет в файле (как в экспорте 2010-2011), объём равен 0
    if target_row_words is None:
        return (0.0, 0.0), (0.0, 0.0)

    cells = merge_cells_in_rotated_row(target_row_words)
    # Находим ячейку с единицей измерения ('тонн', 'т', 'кг')
    unit_idx = next(i for i, c in enumerate(cells) if c in ("тонн", "т", "кг"))
    unit = cells[unit_idx]
    scale = 1.0 / 1000.0 if unit == "кг" else 1.0
    nums = cells[unit_idx + 1 :]

    if has_net_weight:
        # Порядок в 2012-2013: [кол-во1, вес1, стоим1, кол-во2, вес2, стоим2, ...]
        q1, v1 = to_float(nums[0]) * scale, to_float(nums[2])
        q2, v2 = to_float(nums[3]) * scale, to_float(nums[5])
    else:
        # Стандартный порядок: [кол-во1, стоим1, цена1, кол-во2, стоим2, цена2, ...]
        q1, v1 = to_float(nums[0]) * scale, to_float(nums[1])
        q2, v2 = to_float(nums[3]) * scale, to_float(nums[4])

    return (round(q1, 3), round(v1, 1)), (round(q2, 3), round(v2, 1))


def parse_xls_080711(filepath: Path):
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    code_col = df.iloc[:, 1].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    matches = df[code_col.str.lstrip("0") == "80711"]
    if matches.empty:
        return (0.0, 0.0), (0.0, 0.0)

    row = matches.iloc[0]
    unit = str(row.iloc[3]).strip().lower()
    scale = 1.0 / 1000.0 if unit == "кг" else 1.0

    q1, v1 = to_float(row.iloc[4]) * scale, to_float(row.iloc[5])
    q2, v2 = to_float(row.iloc[7]) * scale, to_float(row.iloc[8])
    return (round(q1, 3), round(v1, 1)), (round(q2, 3), round(v2, 1))


def main():
    records = {}  # year -> dict

    for y1, y2, direction, has_net_weight, fname in FILES_SPEC:
        fpath = RAW_DIR / fname
        if fpath.suffix.lower() == ".pdf":
            (q1, v1), (q2, v2) = parse_pdf_080711(fpath, has_net_weight)
        else:
            (q1, v1), (q2, v2) = parse_xls_080711(fpath)

        for y, q, v in [(y1, q1, v1), (y2, q2, v2)]:
            rec = records.setdefault(y, {"year": y})
            q_key, v_key = f"{direction}_tonnes", f"{direction}_usd_k"
            # Для стыковочных лет (2013, 2020) берём более точное значение (в кг -> 3 знака)
            if q_key not in rec or (y == 2013 and direction == "export" and has_net_weight):
                rec[q_key] = q
                rec[v_key] = v

    df = pd.DataFrame(sorted(records.values(), key=lambda r: r["year"]))
    df = df[["year", "import_tonnes", "import_usd_k", "export_tonnes", "export_usd_k"]]

    out_csv = PROCESSED_DIR / "watermelons_2008_2021.csv"
    df.to_csv(out_csv, index=False)
    print(df.to_string(index=False))
    print(f"\nСохранено в: {out_csv}")


if __name__ == "__main__":
    main()