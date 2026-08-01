# LC classification

Share of each institution's call-numbered records in each Library of Congress
class (the first letter of the MARC 050 / 090 call number) — a shared, controlled
scheme, so it compares cleanly across institutions. Only records carrying an LC
call number are counted.

```js
import {lcClassLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
const comparison = FileAttachment("./data/comparison.json").json();
```

```js
shareHeatmap(comparison, "classification", lcClassLabel, {marginLeft: 210})
```
