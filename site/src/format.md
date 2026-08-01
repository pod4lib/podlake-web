# Format

Share of each institution's records of each material type (from the MARC
leader's type-of-record code).

```js
import {recordTypeLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
const comparison = FileAttachment("./data/comparison.json").json();
```

```js
shareHeatmap(comparison, "record_type", recordTypeLabel, {marginLeft: 205})
```
