# LC classification

This chart shows the Library of Congress class — the first letter of the call
number — for each institution's records. The call number is taken from the
first place it appears among several: the standard `050`/`090`, or a local
holdings/item field, which varies by institution (`852`,`950`, `900`). Non-LC
schemes such as Dewey are skipped, and electronic resources typically carry no
call number at all, so the shares are within each institution's LC-classified
records.

See the [completeness](./completeness) chart for a sense of how many records
include an LC Classification. 

```js
import {lcClassLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const comparisonFile = FileAttachment("./data/comparison.json");
const comparison = comparisonFile.json();
```

```js
shareHeatmap(comparison, "classification", lcClassLabel, {marginLeft: 210})
```

```js
provenance({sql: comparison.dimensions.classification.sql, dataUrl: await comparisonFile.url(), dataName: "comparison.json"})
```
