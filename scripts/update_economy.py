import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/"
    "statistics/1.0/data/nama_10_pc"
    "?lang=EN&freq=A&unit=CP_EUR_HAB&na_item=B1GQ&geo=BG"
)

request = Request(URL, headers={"User-Agent": "bgvchisla-data-updater/1.0"})
with urlopen(request, timeout=120) as response:
    data = json.load(response)

if "error" in data or "time" not in data.get("dimension", {}):
    raise RuntimeError("Невалиден отговор от Евростат.")

dimensions = data["id"]
sizes = data["size"]

if any(size != 1 for name, size in zip(dimensions, sizes) if name != "time"):
    raise RuntimeError("Получени са неочаквани допълнителни серии.")

time_index = data["dimension"]["time"]["category"]["index"]
if isinstance(time_index, list):
    time_index = {year: index for index, year in enumerate(time_index)}

values = data.get("value", {})
statuses = data.get("status", {})


def item(container, index):
    if isinstance(container, list):
        return container[index] if index < len(container) else None
    return container.get(str(index))


points = []
for year, index in sorted(time_index.items()):
    value = item(values, index)
    if value is None:
        continue
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RuntimeError("Невалидна числова стойност.")
    points.append({
        "year": int(year),
        "value": value,
        "flag": item(statuses, index)
    })

if not points:
    raise RuntimeError("Няма получени данни. Старият файл се запазва.")

path = Path("economy.json")
economy = json.loads(path.read_text(encoding="utf-8"))

series = {
    "id": "gdp_per_capita_current_eur",
    "title": "БВП на човек по текущи цени",
    "unit": "евро на човек",
    "frequency": "annual",
    "source": "Евростат",
    "dataset": "nama_10_pc",
    "source_url": URL,
    "note": "По текущи цени; не измерва самостоятелно реалния растеж.",
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "points": points
}

economy["series"] = [
    row for row in economy.get("series", [])
    if row["id"] != series["id"]
] + [series]

temporary = path.with_suffix(".tmp")
temporary.write_text(
    json.dumps(economy, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8"
)
temporary.replace(path)
