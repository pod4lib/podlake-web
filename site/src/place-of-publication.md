# Place of publication

This chart shows the place of publication for records from each institution.
The place is taken from the MARC 008 country code). U.S. states, Canadian
provinces, and UK nations are rolled up to their countries.

```js
import {placeLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const comparisonFile = FileAttachment("./data/comparison.json");
const comparison = comparisonFile.json();
```

```js
shareHeatmap(comparison, "country", placeLabel)
```

```js
provenance({sql: comparison.dimensions.country.sql, dataUrl: await comparisonFile.url(), dataName: "comparison.json"})
```
