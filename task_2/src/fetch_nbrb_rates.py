from pathlib import Path
import requests
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

DENOMINATION_DATE = pd.Timestamp("2016-07-01")


def fetch_chunk(cur_id: int, start_date: str, end_date: str) -> list[dict]:
    url = f"https://api.nbrb.by/exrates/rates/dynamics/{cur_id}"
    resp = requests.get(
        url,
        params={"startdate": start_date, "enddate": end_date},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    all_rows = []
    # API НБРБ отдаёт максимум 365 дней за запрос; 09.07.2021 Cur_ID сменился с 145 на 431
    for year in range(2008, 2025):
        if year < 2021:
            chunks = [(145, f"{year}-01-01", f"{year}-12-31")]
        elif year == 2021:
            chunks = [
                (145, "2021-01-01", "2021-07-08"),
                (431, "2021-07-09", "2021-12-31"),
            ]
        else:
            chunks = [(431, f"{year}-01-01", f"{year}-12-31")]

        for cur_id, s_dt, e_dt in chunks:
            data = fetch_chunk(cur_id, s_dt, e_dt)
            all_rows.extend(data)
        print(f"Загружен {year} год (всего записей: {len(all_rows)})")

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["Date"])
    df["rate_raw"] = df["Cur_OfficialRate"].astype(float)

    # Приводим доденоминационные рубли (BYR, до 01.07.2016) к современным BYN (10 000 BYR = 1 BYN)
    df["byn_per_usd"] = df.apply(
        lambda r: r["rate_raw"] / 10000.0 if r["date"] < DENOMINATION_DATE else r["rate_raw"],
        axis=1,
    )
    df["year"] = df["date"].dt.year
    df = df[["date", "year", "byn_per_usd"]].sort_values("date").drop_duplicates("date")

    daily_path = PROCESSED_DIR / "nbrb_usd_daily_2008_2024.csv"
    df.to_csv(daily_path, index=False)

    annual = (
        df.groupby("year", as_index=False)["byn_per_usd"]
        .agg(byn_usd_mean="mean", byn_usd_median="median", byn_usd_min="min", byn_usd_max="max", byn_usd_std="std")
        .round(4)
    )
    annual_path = PROCESSED_DIR / "nbrb_usd_annual_2008_2024.csv"
    annual.to_csv(annual_path, index=False)

    print("\nСреднегодовые курсы BYN/USD (2008-2024):")
    print(annual.to_string(index=False))
    print(f"\nСохранено:\n  - {daily_path}\n  - {annual_path}")


if __name__ == "__main__":
    main()