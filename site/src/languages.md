# Languages

Share of each institution's records in each of the consortium's most common
languages (from the MARC 008 language code).

```js
import {languageLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const comparisonFile = FileAttachment("./data/comparison.json");
const comparison = comparisonFile.json();
```

```js
shareHeatmap(comparison, "language", languageLabel)
```

```js
provenance({sql: comparison.dimensions.language.sql, dataUrl: await comparisonFile.url(), dataName: "comparison.json"})
```
