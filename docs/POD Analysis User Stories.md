## Dashboard Functional Requirements

### **Workbook 1: Comparative Collection Analysis**

User stories 1.1-1.5 compare local collection data to the rest of the POD data (or a subset of that data) to answer questions related to purchasing, retaining, and/or storing resources. These user stories start with the collections of a particular institution and compare them to the holdings of other institutions to decide what holdings to buy, retain, replace, etc. While the users stories in group 2 are different in purpose, they rely on similar data. It's possible that we can meet all of the user needs of groups 1 and 2 in a single workbook (with different dashboards).

See the document [POD Analytics Functions](https://docs.google.com/document/d/18OZXq8l37m1b82XGfHwy1Rj7P6-TJEC_DP4jDgpM1qY/edit?tab=t.0) for descriptions of functions that might be needed to support these user stories.

#### Parameters

* The user will need to be able to select their institution as a parameter to compare against the rest of the database. This might look similar to the other filter needed to select which institutions are in the result set; we will need to do some UX work to make sure the difference is clear to the user.

#### Filters

* A multiple selection dropdown menu so the user can select one or more partners who should be included in the query.

#### Metadata fields

### **Workbook 2: Metadata Analysis**

Group 1 is organized around the theme of collection management and development. User stories 1,3, and 5 involve comparing a local collection (or portion of a local collection) to collections from other POD contributors. The comparison of local collections to the larger POD community record sets will require a distinct technical implementation compared to searching across a faceted set of POD records. Group 2 is organized around the theme of preservation and access. Groups 1 and 2 could be reorganized around technical requirements which would make user stories 1.2 and 1.4 fit well in Group 2\. Group 3 is more about where the metadata comes from, rather than what resources are available and from where.

## User Stories (First Pass)

### **1\. Collection Management & Development**

This group of stories focuses on using collective data to make strategic decisions about building and managing library collections.

1. **User Story:** As a **collection strategist**, I want to **analyze the overlap and uniqueness of our holdings with a specific partner (e.g., ReCap) or the entire consortium**, so that I can **inform collaborative collection development and retention strategies.**  
2. **User Story:** As a **subject specialist**, I want to **query the collective holdings for specific collaborative collection areas (e.g., Brazilian Monographs, Buddhist studies in CJK)**, so that I can **assess the overall strength of our shared collection and identify gaps.**  
3. **User Story:** As a **collection manager** working on a major collection shift (e.g., West stacks project), I want to **determine which of my local titles are also held elsewhere in the consortium**, so that I can **make informed decisions about moving, storing, or weeding materials.**  
4. **User Story:** As an **e-resources librarian**, I want to **check if a print or other permanent copy of a book we license as an ebook exists within the consortium**, so that I can **assess the long-term risk of losing access if the license is cancelled.**  
5. **User Story:** As a **collection manager**, I want to **submit a list of my library's 'lost' or 'missing' items and check their availability across the consortium**, so that I can **make data-driven decisions about whether to replace them.**  
   * **Acceptance Criteria:**  
     * The system can ingest a list of bibliographic identifiers.  
     * The output indicates if the title is held by any other IPLC institution.  
     * The output indicates if the title is available for request via BorrowDirect (requires a query to ReShare).  
     * The output indicates if the title is available in HathiTrust.  
     * The output indicates if the title is likely in the Public Domain.

### **2\. Preservation & Access: Archiving & Digitization**

These stories center on identifying materials that require preservation action to ensure their long-term survival.

1. **User Story:** As a **preservation librarian**, I want to **identify materials that are held by only one or a few partner institutions ("last copies")**, so that I can **prioritize them for preservation and digitization actions.**  
2. **User Story:** As a **data analyst**, I want to **analyze the usage of the MARC 583 field (Preservation Action) across the consortium**, so that I can **understand and report on our collective preservation commitments and activities.**  
3. **User Story:** As a **preservation librarian**, I want to **identify US serials held by the consortium that are not in HathiTrust**, so that I can **perform a public domain analysis to find candidates for digitization.**

### **3\. Cataloging & Data Quality**

These stories focus on leveraging the collective dataset to improve the quality and efficiency of cataloging.

1. **User Story:** As a **cataloging manager**, I want to **run an analysis on the MARC 040 field (Cataloging Source) across all partner records**, so that I can **understand the origins and flow of our collective cataloging data.**  
2. **User Story:** As a **cataloger**, I want to **find records for complex items (e.g., 'bound-withs') from other partner libraries**, so that I can **use their work as a model to improve or create records in my local system.**  
3. **User Story:** As a **reparative cataloging specialist**, I want to **perform text-based queries across the entire dataset to identify potentially harmful or outdated language in catalog records**, so that I can **prioritize items for reparative description work.**  
4. **User Story:** As a **metadata analyst**, I want to **identify and analyze the usage of IIIF manifests in MARC 856 fields**, so that I can **assess the adoption of IIIF across the consortium and support related discovery projects.**  
5. **User Story:** As a… I need to find a specific set of records (e.g. all cataloging records from the CRL Latin American collections) so I can extract these records and ingest them into my system.

