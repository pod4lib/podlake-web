# Format

This chart tallies each institution's records by material type (from the MARC
leader's type-of-record code).

```js
import {recordTypeLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const comparisonFile = FileAttachment("./data/comparison.json");
const comparison = comparisonFile.json();
```

```js
shareHeatmap(comparison, "record_type", recordTypeLabel, {marginLeft: 205, width})
```

```js
provenance({sql: comparison.dimensions.record_type.sql, dataUrl: await comparisonFile.url(), dataName: "comparison.json"})
```
