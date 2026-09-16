import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

import MapContainer from "./components/MapContainer.vue";

const app = createApp(MapContainer);
app.use(ElementPlus);
app.mount("#app");

