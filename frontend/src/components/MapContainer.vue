<template>
  <div class="map-wrapper">
    <div class="filter-panel">
      <el-select v-model="riskLevel" placeholder="选择风险等级" size="small">
        <el-option label="全部" value="all" />
        <el-option label="高风险" value="high" />
        <el-option label="中风险" value="medium" />
        <el-option label="低风险" value="low" />
      </el-select>
      <el-date-picker
        v-model="timeRange"
        type="datetimerange"
        start-placeholder="开始"
        end-placeholder="结束"
        size="small"
      />
      <el-button type="primary" size="small" @click="filterHotspots">筛选</el-button>
    </div>
    <div id="risk-map" class="map-canvas"></div>
    <el-table :data="alertList" size="small" @row-click="handleRowClick">
      <el-table-column prop="areaName" label="风险区域" />
      <el-table-column prop="riskLevel" label="等级" />
      <el-table-column prop="timeSlice" label="时间段" />
      <el-table-column prop="giScore" label="Z值" />
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" @click.stop="exportSingle(row)">导出</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const riskLevel = ref("all");
const timeRange = ref([]);
const alertList = reactive([]);
let map;
let hotspotLayer;

const riskStyles = {
  high: { color: "#d32f2f", fillColor: "#d32f2f", fillOpacity: 0.6, weight: 2 },
  medium: { color: "#f57c00", fillColor: "#f57c00", fillOpacity: 0.5, weight: 2 },
  low: { color: "#fbc02d", fillColor: "#fbc02d", fillOpacity: 0.4, weight: 2 },
};

const AMAP_KEY = "a7fd9560ffd58dcc12262f8f3d834b53";

function initMap() {
  map = L.map("risk-map").setView([28.194, 113.019], 12);
  L.tileLayer(
    `https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scl=1&style=8&x={x}&y={y}&z={z}&key=${AMAP_KEY}`,
    {
      subdomains: ["1", "2", "3", "4"],
      attribution: "&copy; 高德地图",
    }
  ).addTo(map);
  hotspotLayer = L.layerGroup().addTo(map);
}

async function loadHotspots(params = "") {
  const res = await fetch(`/api/hotspots/geojson?${params}`);
  const geojson = await res.json();
  renderHotspots(geojson);
  alertList.splice(0, alertList.length, ...geojson.features.map((f) => ({
    areaId: f.id,
    areaName: f.properties.areaName || `区域${f.id || ""}`,
    riskLevel: f.properties.risk_level,
    timeSlice: f.properties.time_slice,
    giScore: f.properties.gi_score,
    geometry: f.geometry,
  })));
}

function renderHotspots(geojson) {
  hotspotLayer.clearLayers();
  L.geoJSON(geojson, {
    style: (feature) => riskStyles[feature.properties.risk_level] || riskStyles.low,
    onEachFeature: (feature, layer) => {
      layer.bindPopup(
        `
        <strong>${feature.properties.areaName || "风险区域"}</strong><br />
        等级：${feature.properties.risk_level}<br />
        时间：${feature.properties.time_slice}<br />
        Z值：${feature.properties.gi_score?.toFixed?.(2) ?? "-"}
        `
      );
    },
  }).addTo(hotspotLayer);
}

function buildParams() {
  const params = new URLSearchParams();
  params.append("riskLevel", riskLevel.value);
  if (timeRange.value?.length === 2) {
    params.append("startTime", timeRange.value[0].toISOString());
    params.append("endTime", timeRange.value[1].toISOString());
  }
  return params.toString();
}

function filterHotspots() {
  loadHotspots(buildParams());
}

function handleRowClick(row) {
  const layer = L.geoJSON(row.geometry);
  map.fitBounds(layer.getBounds(), { padding: [24, 24] });
}

function exportSingle(row) {
  const data = [
    "风险区域ID,风险等级,时间范围,热点Z值,中心经度,中心纬度",
    `${row.areaId},${row.riskLevel},${row.timeSlice},${row.giScore},${JSON.stringify(
      row.geometry
    )}`,
  ].join("\n");
  const blob = new Blob([data], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `hotspot_${row.areaId || Date.now()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

onMounted(() => {
  initMap();
  loadHotspots();
});
</script>

<style scoped>
.map-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.map-canvas {
  height: 520px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}
.filter-panel {
  display: flex;
  gap: 12px;
  align-items: center;
}
</style>

