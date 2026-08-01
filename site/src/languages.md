# Languages

Share of each institution's records in each of the consortium's most common
languages (from the MARC 008 language code).

```js
import {languageLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
const comparison = FileAttachment("./data/comparison.json").json();
```

```js
shareHeatmap(comparison, "language", languageLabel)
```
