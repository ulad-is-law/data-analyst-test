import json
import urllib.request
from pathlib import Path

import pandas as pd

# Координаты Минска (географический центр и главный рынок потребления РБ)
LATITUDE = 53.9000
LONGITUDE = 27.5667
START_DATE = "2008-01-01"
END_DATE = "2024-12-31"


def fetch_open_meteo_daily() -> pd.DataFrame:
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        f"&start_date={START_DATE}&end_date={END_DATE}"
        "&daily=temperature_2m_mean,temperature_2m_max,precipitation_sum"
        "&timezone=Europe%2FMinsk"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    daily = payload["daily"]
    df_daily = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "temp_mean": daily["temperature_2m_mean"],
        "temp_max": daily["temperature_2m_max"],
        "precip_mm": daily["precipitation_sum"],
    })
    return df_daily


def aggregate_summer_weather(df_daily: pd.DataFrame) -> pd.DataFrame:
    df_d = df_daily.copy()
    df_d["year"] = df_d["date"].dt.year
    df_d["month"] = df_d["date"].dt.month

    # Летний сезон: июнь - август
    summer = df_d[df_d["month"].isin([6, 7, 8])].copy()
    summer["is_hot_25"] = (summer["temp_max"] >= 25.0).astype(int)

    # Пик сезона арбузов: июль - август
    jul_aug = (
        df_d[df_d["month"].isin([7, 8])]
        .groupby("year", as_index=False)["temp_mean"]
        .mean()
        .rename(columns={"temp_mean": "jul_aug_temp_mean"})
    )

    annual = (
        summer.groupby("year", as_index=False)
        .agg(
            summer_temp_mean=("temp_mean", "mean"),
            hot_days_25=("is_hot_25", "sum"),
            summer_rain_mm=("precip_mm", "sum"),
        )
    )

    res = pd.merge(annual, jul_aug, on="year", how="left")
    res["summer_temp_mean"] = res["summer_temp_mean"].round(2)
    res["jul_aug_temp_mean"] = res["jul_aug_temp_mean"].round(2)
    res["summer_rain_mm"] = res["summer_rain_mm"].round(1)

    cols = ["year", "summer_temp_mean", "jul_aug_temp_mean", "hot_days_25", "summer_rain_mm"]
    return res[cols]


def main() -> None:
    task_root = Path(__file__).resolve().parent.parent
    out_dir = task_root / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Скачиваю архив погоды Open-Meteo (Минск, 2008-2024)...")
    df_daily = fetch_open_meteo_daily()
    df_annual = aggregate_summer_weather(df_daily)

    daily_path = out_dir / "belarus_weather_daily_2008_2024.csv"
    annual_path = out_dir / "belarus_weather_2008_2024.csv"

    df_daily.to_csv(daily_path, index=False)
    df_annual.to_csv(annual_path, index=False)

    print(f"Готово! Сохранено строк по годам: {len(df_annual)}")
    print(f" -> {annual_path}")
    print(df_annual.to_string(index=False))


if __name__ == "__main__":
    main()