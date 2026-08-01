# Place of publication

Share of each institution's records published in each place (from the MARC 008
country code). U.S. states, Canadian provinces, and UK nations are rolled up to
their countries.

```js
import {placeLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
const comparison = FileAttachment("./data/comparison.json").json();
```

```js
shareHeatmap(comparison, "country", placeLabel)
```
