July 22, 2025

This is a compendium of notes on POD Data Analytics to be used as prep for the Fall 2025 workcycle. There is quite a bit of repetition across the many times this was discussed. Please don’t hesitate to flag any items that need more attention or exposition. 

# March 2025: POD Board Discussion 

Redux from reporting & analytics use cases: 

1. Looking for holdings analysis to inform & prioritize preservation actions – what is truly “rare”?  
2. Systematic review of lost and missing items  
   1. Examine what might be in POD to better know what is available  
3. 040 analysis – source of catalog records for IPLC  
4. Stanford: West stacks collection shift. What’s in network?   
5. One potential area of concern as we move more towards ebook licenses rather than print book purchases:   
6. Potential collab with ReCap and its effort to identify the overlap in ReCap holdings.  
   1. Add in NYPL data to POD (\!) 

# February 2025: POD Board Discussion with IPLC SMEs

* Andy Hart, Penn:   
  * Looking for holdings analysis to inform & prioritize preservation actions – what is truly “rare”?  
  * Would want to do a whole view on   
  * Also look at what has been digitized / mass digitized.   
* Jim Hahn:   
  * Here is the trial code I’m iterating on:  
  * [https://github.com/jimfhahn/pod-pyspark-notebook](https://github.com/jimfhahn/pod-pyspark-notebook)  
  * **Data Loading:**  
  * The MARC data is loaded into Parquet format using marctable. Parquet is a columnar storage file format optimized for use with big data processing frameworks.  
  * **Data Processing:**  
  * The Parquet files are then loaded into Spark. Using PySpark SQL, various data processing tasks are performed to transform and analyze the data.  
* John Mark Ockerbloom  
  * Also helping with Serials Backfiles  
  * Possibly relevant here: I  did a public domain analysis of HathiTrust-held US serials, showing what’s potentially in the public domain and what’s currently openly available from them or other digital providers.  Here’s the table: https://onlinebooks.library.upenn.edu/webbin/backfile/hathitrust-us    (This table doesn’t use POD data, but I could imagine other tables that did.)  
  * One potential area of concern as we move more towards ebook licenses rather than print book purchases: Do we want to track whether someone else has a print or otherwise permanent copy of the books we’ve e-licensed, so we know we can fall back on those copies if we lose access to the licensed e-versions?	  
* Chris Killhefer & Daniel Dollar, Yale:   
  * Systematic review of lost and missing items  
  * Examine what might be in POD to better know what is available  
  * Do a big catch up and then run on an annual basis  
  * What number of items?   
    * General rule: “If there is one item available via BD, then we don’t need to replace it.“  
    * Also if item is in Public Domain or if item is available via Hathi, probably wouldn’t replace it  
    * Subject specialists can make the decision though  
  * Something like 80% of titles had hits in POD  
  * Do this as a workflow step   
  * They can provide full bib data for what they’re missing  
    * Is it at an IPLC institution?recaiplc  
    * Is it available for request via BD?   
      * Note this would need an additional query to ReShare  
    * Is it in Hathi?   
    * Is it public domain?   
* Stanford  
  * 040 analysis – source of catalog records for IPLC  
  * West stacks collection shift. What’s in network?   
* Nora:   
  * Boundwiths are a big challenge, especially in Alma  
  * Can POD help with this?   
  * The data is there. Just not parsed right in Alma?   
  * Could I go steal the records from POD?   
  * Or mine POD Data to see what other institutions have done?   
* What could POD use?   
  * Support for transactions for queries  
    * Take the POD Data, ETL it with MARC tables into Parquet  
      * Note: Some libraries have weird data encodings  
    * Then do SQL queries for what you’re interested in  
  * Add in Hathi records  
    * Also, is it available as Public Domain  
  * Do a PD check for things that are not in Hathi  
    * Use the Hathi methodology?   
  * Clustering / reconciliation   
    * Is this the same title as that?   
    * Is this an item or holding for that?   
  * One potential area of concern as we move more towards ebook licenses rather than print book purchases: Do we want to track whether someone else has a print or otherwise permanent copy of the books we’ve e-licensed, so we know we can fall back on those copies if we lose access to the licensed e-versions?  
  * Potential collab with ReCap and its effort to identify the overlap in ReCap holdings.  
    * Add in NYPL data to POD (\!)   
  * J. Hahn has experimented with processes for spawning ETL from POD.  Assemble a technical collaboration to move this forward to support further use cases on collection analytics and related operational needs.  
    * Is already working on an Airflow  
  * Annual could be just as fresh as is needed. 

# POD Liaisons Discussion

[POD Data Analysis Kick-Off Conversation](https://docs.google.com/document/d/1sKRcAKrj74lMay-xJ6fbMvuvcF2REpwy3XmPkw7jvsg/edit?tab=t.0)

# POD Use Cases Round Up – 2024

* Interesting to the degree we can query the data lake for analytics, decision support  
  * Not a big effort in and of itself.   
* Need to dust off the reporting use cases and see which are doable and compelling  
  * Brill  
  * Other collaborative collections  
    * Brazilian Monographs  
    * Latin American artists  
  * Buddhist studies in CJK  
  * Art & Architecture acquisitions across IPLC  
  * Lost items  
  * IIIF in 856s  
  * Deduped record set of all IPLC holdings  
  * Collection management (i.e.: retention intent, digitization/preservation intent)  
    * 583 Analysis  
  * Reparative cataloging / harmful language  
    * Remember National Humanities Center AI grant interest to partner with Duke. Would POD be a good use case for future proposal 

# POD Use Cases Round Up – January 2024

* OA record feed & Google Books  
  * See [https://onlinebooks.library.upenn.edu/](https://onlinebooks.library.upenn.edu/)   
    * John Mark Ockerbloom’s collection of 3M curated OA books  
    * These records aren’t in MARC at the moment  
  * [Vendor record enhancement](https://docs.google.com/document/d/1F7-4xpQqXOoFgPA3Ys0dIxBZnWCHafsgWtTXjDEsBi4/edit)  
    * TSG probably thinking about this as not a POD initiative  
    * Talk to Jason Kovari as POD liaison  
    * Likely a contractual issue with vendors and data sharing  
  * LC MARC distribution (see [MDS](https://www.loc.gov/cds/products/marcDist.php))  
  * 040 Analysis  
  * Other data analysis questions  
    * Brill  
    * Other collaborative collections  
      * Brazilian Monographs  
      * Latin American artists  
    * Buddhist studies in CJK  
    * Art & Architecture acquisitions across IPLC  
    * Lost items  
    * IIIF in 856s  
    * Deduped record set of all IPLC holdings  
    * Collection management (i.e.: retention intent, digitization/preservation intent)  
  * Reparative cataloging / harmful language  
    * Remember National Humanities Center AI grant interest to partner with Duke. Would POD be a good use case for future proposal   
  * Open Metadata Framework  
  * Local discovery  
  * Gold Rush, feed to…  
    * Compare notes with BTAA?  
* Reparative Discussion:   
  * Who is interested?   
    * Stanford: Tom & Ann Myers  
    * Brown: Melissa & Nora, Katrina Jackson  
    * Penn:   
    * Cornell: Simeon, Jason Kovari and Dianne Dietrich (likely)  
    * Duke:   
    * Harvard: Isabel Quintana & Claire DeMarco  
    * TRLN: ask Kelly Ferrell  
    * NORTH: ???

# POD Board Notes: October 2022

* Reporting & Analytics Summit – what are the kinds of things people want to query and why? Could inform incremental reporting or analytics for POD future development.   
* See also the dashboard produced from first CDG effort:   
  * [https://public.tableau.com/app/profile/sarah.tudesco/viz/IPLCComparativeCollectionAnalysis-TownHallDashboard/CopyAnalysisDashboard?publish=yes](https://public.tableau.com/app/profile/sarah.tudesco/viz/IPLCComparativeCollectionAnalysis-TownHallDashboard/CopyAnalysisDashboard?publish=yes) 

# POD Board – May 3, 2022

* Report on [IPLC meeting for Coordinated Approval Plan](https://docs.google.com/document/d/1-EBkXMLEql8TpKKsHkP4hCQuGaLMUpzRr_bTDnRRuzY/edit)  
  * 1\. POD could be a very useful data broker for the common approval plan they hope to implement with GOBI / Brill.   
  * 2\. POD could aggregate MARC records for Brill acquisitoins (about 1500? per year?)   
  * 3\. POD could distribute MARC records to local ILSes  / discovery environments  
  * 4\. POD could distribute MARC records to reporting / analytics environments for collections analysis / reporting  
  * 5\. we should look at developing a Blacklight for collections analysis as a next step  
  * In short, seems like a great fit and low hanging fruit for a new use case that is halfway between collections development and resource access.   
* David Bietila visit: [discuss survey on Brill project](https://docs.google.com/document/d/1rufGeVM2QvNSVRWQy_upSNBnYCEDKtT68l7L7QXkkPs/edit)  
* May 17 \= [POD:North Meeting](https://docs.google.com/document/d/1_kwgqGwUDJDKjICEUj9bvMwMP4U2DF5VLhnx7kh2rfY/edit#heading=h.g3x9g9yfuo19)  
* Offer of ShareVDE tenant for IPLC from Michele Casalini  
  * Next step: set up a demo  
    * And establish feasibility, desirability, criteria for assessment & success  
  * Attendees: POD Board \+ extras (Hahn, Schreur, Kovari, Ockerbloom) \+ IPLC staff (GB, GC)?  
    * Record the meeting?  
    * Plan for 2nd meeting to include heads of TS, etc.?  
* [583 field usage / reporting](https://docs.google.com/document/d/1-Jp3E40WFI27VzsxyeFxqxfqTz0-VmeDqbP6IbSKLZg/edit#heading=h.hgluoaoxxxbh)

# Possibly Related: POD for Horizon Reports. 

**Please describe your project in 70 words or less. If selected, this text will be the basis of the project description in the 2022 Horizon Report.**

POD, the Platform for Open Data, provides infrastructure needed to collect, house, and syndicate collective library metadata of multiple institutions. POD positions consortial data as a strategic asset by facilitating its reuse and enabling new service integrations.The project uses open, iterative development in multi-institution agile teams to meet multiple needs and enable innovation in ways that cannot be done through one-off solutions or relying on vendors and external systems. 

**Why should we choose your project as an exemplar for the 2022 Data and Analytics Horizon Report?\***

Aggregation and manipulation of data across institutions is a core part of information discovery and access services and part of the need for institutions to approach core operations collaboratively in the future.  

POD creates a data architecture and capacity for sustaining and growing intra-institutional service value. POD will be **modular and open** in its architecture both internally for resilience, and externally to complementary solutions which accommodate data and enrichments from multiple sources.

Collection sharing is both an **operational service and a strategic concern** as is evidenced by market acquisitions and consolidations.

POD **benefits the marketplace and community** for resource-sharing technologies by providing a check and alternative to an otherwise unconstrained and increasingly consolidated market of commercial services. It complements and potentially accelerates usable open-source technologies without locking one into any one solution.

POD empowers institutions to first “come as they are”; instead of requiring data standards that are onerous to agree on, effect, and audit in the style of a data warehouse. The level of effort required of partners is determined by their ambition as consumers, more than being imposed by becoming a contributor.

POD emphasizes open design, open progress reports and open participation, because the best work is done in the open. Other institutions and collaborations may use POD outputs or add to them, even if they are not following an open paradigm.

POD has been selected by the Ivy Plus Library Confederation as the data source for its implementation of the new BorrowDirect resource sharing platform powered by ReShare. POD is in active conversation with numerous national and regional consortia and organizations exploring contributing data to and using POD.

**Anything else you'd like us to know about this project/initiative? (50 words of less)**

POD makes **quick and strategic progress** on discovery. Its modular design and open principles will accommodate input and participation from any partner, and will benefit all partners and beyond. It is a platform rather than a point solution and will serve as a base for current needs and future efforts. 

**How does your project/initiative align with your institution's strategic goals?\***

POD greatly reduces the friction involved in aggregating, storing, and sharing bibliographic and holdings data from across the IPLC. POD obviates unnecessary and potentially redundant costs and effort in supporting IPLC data-dependent initiatives and programs. POD opens the door to innovative use and reuse of the partnership’s data assets, and provides flexibility in the choice and resilience of software solutions for discovery and related services, including the current proposals for a shared index.     
