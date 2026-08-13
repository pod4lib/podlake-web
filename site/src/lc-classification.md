# LC classification

This chart shows the Library of Congress class — the first letter of the call
number — for each institution's records. The call number is taken from the
first place it appears among several: the standard `050`/`090`, or a local
holdings/item field, which varies by institution (`852`, `950`, `900`, …).

We err toward *not* claiming an LC classification: the `852` holdings field is
only trusted when its scheme indicator says LC (many hold Dewey, NLM, or local
schemes instead), Dewey and NLM numbers are skipped, and only the 21 letters LC
actually uses are counted. Electronic resources typically carry no call number
at all. So the shares below are within each institution's *confirmed* LC-classified
records, and each column sums to ~100%.

See the [completeness](./completeness) chart for how many records have a
confirmed LC classification — a figure that is deliberately conservative.

```js
import {lcClassLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const comparisonFile = FileAttachment("./data/comparison.json");
const comparison = comparisonFile.json();
```

```js
shareHeatmap(comparison, "classification", lcClassLabel, {marginLeft: 210, width})
```

```js
provenance({sql: comparison.dimensions.classification.sql, dataUrl: await comparisonFile.url(), dataName: "comparison.json"})
```
