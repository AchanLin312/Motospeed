"""
基于示例数据 test_data.csv 生成交互式 HTML 热点地图。

运行方式：
    python scripts/generate_hotspot_map.py
输出：
    outputs/risk_hotspots.html
"""
from pathlib import Path

import folium
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "test_data.csv"
OUTPUT_FILE = ROOT / "outputs" / "risk_hotspots.html"
OUTPUT_FILE.parent.mkdir(exist_ok=True)


def main():
    df = pd.read_csv(DATA_FILE)
    df["Speed"] = pd.to_numeric(df["Speed"], errors="coerce").fillna(0)
    df["risk_level"] = df["Speed"].apply(lambda v: "高风险" if v > 0.8 else "中风险" if v > 0.6 else "低风险")
    center = [df["Y_position"].mean(), df["X_position"].mean()]

    fmap = folium.Map(location=center, zoom_start=16, tiles="OpenStreetMap", control_scale=True)

    color_map = {"高风险": "#d32f2f", "中风险": "#f57c00", "低风险": "#fbc02d"}
    for _, row in df.iterrows():
        folium.CircleMarker(
            location=[row["Y_position"], row["X_position"]],
            radius=6 if row["risk_level"] == "高风险" else 4,
            color=color_map[row["risk_level"]],
            fill=True,
            fill_color=color_map[row["risk_level"]],
            fill_opacity=0.7,
            popup=folium.Popup(
                f"""
                <b>轨迹ID：</b>{row['ID']}<br>
                <b>速度：</b>{row['Speed']:.3f}<br>
                <b>时间：</b>{row['Time']}<br>
                <b>风险等级：</b>{row['risk_level']}
                """,
                max_width=250,
            ),
        ).add_to(fmap)

    fmap.save(str(OUTPUT_FILE))
    print(f"已生成 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

