"""F5 전에 합성 DB와 로컬 config를 준비한다. 기존 사용자 파일은 보존한다."""

import json
from pathlib import Path
import sqlite3


# 모델 호출이나 비밀값 로딩 없이, 저장소 안의 Git 제외 경로만 준비한다.
root = Path(__file__).resolve().parents[1]
folder = root / "runs/local-debug"
folder.mkdir(parents=True, exist_ok=True)
database = folder / "orders.sqlite"
if not database.exists():
    # 새 파일일 때만 데이터를 넣어 F5를 반복해도 사용자의 DB를 초기화하지 않는다.
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE orders(order_id TEXT, ordered_at TEXT, order_total_cents INTEGER)")
        connection.executemany("INSERT INTO orders VALUES (?, ?, ?)", [
            ("debug-1", "2025-01-13", 1999),
            ("debug-2", "2025-01-14", 2000),
            ("debug-3", "2025-01-19", 3000),
            ("debug-4", "2025-01-20", 5000),
        ])
    connection.close()

config = folder / "runtime.json"
if not config.exists():
    # 예시의 계약·예산을 그대로 사용하고 DB 경로만 로컬 파일로 바꾼다.
    settings = json.loads((root / "configs/runtime.example.json").read_text(encoding="utf-8"))
    settings["database"]["path"] = "orders.sqlite"
    with config.open("x", encoding="utf-8") as stream:
        json.dump(settings, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

print("Debug data ready: runs/local-debug (existing files preserved).")
