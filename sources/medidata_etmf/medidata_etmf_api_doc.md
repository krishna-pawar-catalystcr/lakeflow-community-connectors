# **Medidata eTMF API Documentation**

## **Authorization**

### Chosen Method: MAuth (Medidata Authentication)

Medidata uses a proprietary authentication mechanism called **MAuth** — a request-signing protocol similar to AWS Signature V4. All API requests must be signed using an RSA private key associated with a registered application UUID.

### Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `app_uuid` | string (UUID) | ✅ Yes | The application UUID registered in Medidata's MAuth system. Identifies the calling application. |
| `private_key` | string (PEM) | ✅ Yes | RSA private key in PEM format used to sign requests. Stored as a file in DBFS/FileStore. |
| `client_division_scheme_uuid` | string (UUID) | ✅ Yes | Identifies the client division scheme (organization/tenant) for scoping API requests. |

### Auth Placement

- **Request signing**: MAuth signs each HTTP request using the `app_uuid` and `private_key`. The signature is added to request headers automatically by the `mauth-client` Python library.
- **API version header**: `Mcc-Version: v2019-04-12` — required on all requests.
- **Accept header**: `Accept: application/json` — required for JSON responses.
- **Query parameter**: `client_division_scheme_uuid` is passed as a query parameter on each API call.

### Python Authentication Example

```python
from mauth_client.requests_mauth import MAuth
import requests

# Initialize MAuth
app_uuid = "40b93548-b79f-4ac0-82ec-005d965e21b5"  # From secret scope
private_key = open("/path/to/private_key.pem").read()  # RSA PEM key

mauth = MAuth(app_uuid, private_key)
headers = {"Accept": "application/json", "Mcc-Version": "v2019-04-12"}

# Make authenticated request
response = requests.get(
    "https://api.mdsol.com/fetch_reports",
    auth=mauth,
    headers=headers,
    params={"client_division_scheme_uuid": "2bb466e6-e8bb-475f-b6a0-a25c89034052"}
)
```

### Dependencies

- **Python package**: `mauth-client` (install via `pip install mauth-client`)
- **Additional packages**: `openpyxl` (for parsing Excel report content), `flatten_json` (optional, for nested JSON handling)

### Secret Storage (Databricks)

Secrets are stored in a Databricks secret scope named `medidata_etmf_{environment}` (e.g., `medidata_etmf_production`):

| Secret Key | Description |
|-----------|-------------|
| `app_uuid` | Application UUID for MAuth |
| `client_division_uuid` | Client division UUID |
| `client_division_scheme_uuid` | Client division scheme UUID (used in API params) |
| `private_key_path` | DBFS path to the RSA private key file (e.g., `/FileStore/shared_uploads/.../MEDI_PRIVATEKEY.key`) |

---

## **Object List**

The Medidata eTMF API exposes data through **report-based extraction** rather than direct table/object APIs. Reports are generated within the Medidata eTMF system and retrieved via the API. The object list is **not directly discoverable via a single API call** — instead, reports are listed via the `GET /fetch_reports` endpoint and filtered by `systemFolderTypeLocalized` to identify report types.

### Available Report Types (Objects)

| Object/Report Name | `systemFolderTypeLocalized` Value | Description | Report Name Pattern |
|---------------------|----------------------------------|-------------|---------------------|
| **eTMF Document Full Details** | `eTMF Document Full Details` | Comprehensive document-level details including state, workflow, dates, and metadata for all eTMF documents across studies. | `*_KPI Full Details` |
| **eTMF Filed Documents** | `eTMF Filed Documents` | Summary of filed/finalized documents with folder paths, zones, sections, and creation metadata. | `*_KPI Total Filed Docs` |
| **KPI Rejections** | `Rejections` | Document rejection records including rejection reason, reviewer, dates, and finalization state. | `All Studies_KPI Rejections` |

### Report Discovery

Reports are discovered via the `GET /fetch_reports` endpoint. Each report element contains:
- `uuid` — Unique identifier for the report file (FSI UUID)
- `name` — Report name (used for pattern matching)
- `systemFolderTypeLocalized` — Report type classification
- `updatedAt` — Timestamp of last update
- `createdAt` — Timestamp of creation

Reports are **per-study** — each study generates its own set of reports. The ingestion process:
1. Fetches all reports within a time window
2. Filters by name pattern (regex: `All Studies_KPI Rejections|.*_KPI Full Details|.*_KPI Total Filed Docs`)
3. Groups by matched study and takes the **latest version** (by `updatedAt`)
4. Extracts UUIDs grouped by report type

### Example: Discovering Reports

```python
url = "https://api.mdsol.com/fetch_reports"
payload = {
    "client_division_scheme_uuid": client_division_scheme_uuid,
    "show_obsoleted": False,
    "created_at_from": 1764547200000,  # Epoch milliseconds
    "created_at_to": 1764633599000,    # Epoch milliseconds
    "pageSize": 1000,
    "pageStart": 0
}

response = requests.get(url, auth=mauth, headers=headers, params=payload)
data = response.json()
elements = data['children']['elements']  # List of report objects
has_next_page = data['children']['hasNextPage']  # Boolean for pagination
```

---

## **Object Schema**

There is **no API endpoint** to retrieve object schemas dynamically. Schemas are **static** and defined by the Excel report structure returned by the Medidata eTMF system. The schemas below are derived from actual API responses and the downstream lakehouse table definitions.

### eTMF Document Full Details — Schema

This is the most comprehensive report with ~123 columns in raw format. The key columns used for ingestion are:

| Column Name (API/Excel) | Mapped Name | Type | Nullable | Description |
|--------------------------|-------------|------|----------|-------------|
| `Document Identifier` | `document_id` | string | Yes | Unique document identifier within the eTMF system |
| `Level` | `level` | string | Yes | Hierarchy level (Study, Country, Site) |
| `Study` | `study` | string | Yes | Clinical trial study identifier (e.g., `CTX-009-002`) |
| `Environment` | `environment` | string | Yes | Study environment (`Production`, `Development`) |
| `Site` | `site` | string | Yes | Clinical site identifier |
| `Folder Path` | `folder_path` | string | Yes | Full folder path in eTMF hierarchy |
| `Zone` | `zone` | string | Yes | TMF Reference Model zone classification |
| `Artifact #` | `artifact` | string | Yes | TMF artifact number |
| `Name` | `name` | string | Yes | Document name |
| `Version` | `version` | string | Yes | Document version number |
| `State` | `state` | string | Yes | Document workflow state (e.g., `ACCEPTED`, `PENDING`, `REJECTED`) |
| `WF Type` | `wf_type` | string | Yes | Workflow type (e.g., `File Document to TMF`, `Standard Workflow`) |
| `Initiator` | `initiator` | string | Yes | Workflow initiator |
| `Created On (User)` | `created_by` | string | Yes | User who created the document |
| `Edit Completed / Rejected By` | `edit_completed_rejected_by` | string | Yes | User/timestamp of edit completion or rejection. Format: `"username, ddMMMyyyy HH:mm:ss GMT"` |
| `Created On (Date/Time)` | `created_at` | string | Yes | Document creation timestamp. Format: `ddMMMyyyy HH:mm:ss GMT` |
| `Document Property: Document Date` | `document_date` | string | Yes | Document date property. Format: `ddMMMyyyy` |

**Additional raw columns** (not mapped in current ingestion but present in raw Excel, ~123 total):
- `Parent Folder`, `QC Review Status`, and many others depending on the eTMF configuration.

### eTMF Filed Documents — Schema

All columns are ingested with lowercase/underscore naming convention (`column_name = original.lower().replace(" ", "_")`).

| Column Name (API/Excel) | Mapped Name | Type | Nullable | Description |
|--------------------------|-------------|------|----------|-------------|
| `Document Name` | `document_name` | string | Yes | Name of the filed document |
| `Folder Path` | `folder_path` | string | Yes | Full folder path in eTMF hierarchy |
| `Study` | `study` | string | Yes | Clinical trial study identifier |
| `Country` | `country` | string | Yes | Country associated with the document |
| `Site` | `site` | string | Yes | Clinical site identifier |
| `Zone` | `zone` | string | Yes | TMF Reference Model zone |
| `Section` | `section` | string | Yes | TMF section classification |
| `Artifact #` | `artifact_#` | string | Yes | TMF artifact number |
| `Format` | `format` | string | Yes | Document format/file type |
| `Created On` | `created_on` | string | Yes | Creation timestamp |
| `Created By` | `created_by` | string | Yes | User who created the document |
| `Document Title` | `document_title` | string | Yes | Title of the document |
| `Version` | `version` | string | Yes | Document version |
| `Updated On` | `updated_on` | string | Yes | Last update timestamp |

**Note**: The `uuid` column is added during ingestion (not from the Excel file) to track which FSI UUID (report file) the row originated from.

### KPI Rejections — Schema

All columns are ingested with lowercase/underscore naming convention.

| Column Name (API/Excel) | Mapped Name | Type | Nullable | Description |
|--------------------------|-------------|------|----------|-------------|
| `Document Name` | `document_name` | string | Yes | Name of the rejected document |
| `Folder Path` | `folder_path` | string | Yes | Full folder path |
| `Rejected Date` | `rejected_date` | string | Yes | Date of rejection |
| `Rejected By` | `rejected_by` | string | Yes | User who rejected the document |
| `Rejection Reason` | `rejection_reason` | string | Yes | Reason for rejection |
| `Comment` | `comment` | string | Yes | Additional rejection comments |
| `Open` | `open` | string | Yes | Whether the rejection is still open |
| `Finalized Version` | `finalized_version` | string | Yes | Version number when finalized |
| `Finalized Document State` | `finalized_document_state` | string | Yes | Document state after finalization |
| `Owner` | `owner` | string | Yes | Document owner |
| `Version` | `version` | string | Yes | Document version |
| `Study` | `study` | string | Yes | Clinical trial study identifier |
| `Site` | `site` | string | Yes | Clinical site identifier |

**Note**: The `uuid` column is added during ingestion to track report origin.

---

## **Get Object Primary Keys**

There is **no API endpoint** for retrieving primary keys. Primary keys are determined based on business logic and the data structure.

| Object | Primary Key | Notes |
|--------|-------------|-------|
| eTMF Document Full Details | `document_id` + `fsi_uuid` | `document_id` (Document Identifier) uniquely identifies a document within a study. Combined with `fsi_uuid` to handle cross-report deduplication. |
| eTMF Filed Documents | `document_name` + `folder_path` + `study` + `uuid` | Composite key — no single unique identifier in the raw data. |
| KPI Rejections | `document_name` + `folder_path` + `rejected_date` + `uuid` | Composite key — a document may be rejected multiple times. |

**Note**: These are inferred primary keys based on the data structure. The Medidata eTMF API does not provide explicit primary key metadata. The `uuid` (FSI UUID) is appended during ingestion to distinguish rows from different report files.

---

## **Object's Ingestion Type**

| Object | Ingestion Type | Rationale |
|--------|---------------|-----------|
| eTMF Document Full Details | `snapshot` | Reports represent a point-in-time snapshot of all documents. No incremental cursor available — the full report is re-generated each time. Current ingestion truncates and reloads. |
| eTMF Filed Documents | `snapshot` | Same as above — full report snapshot with no change tracking. |
| KPI Rejections | `snapshot` | Same as above — full report snapshot. |

**Why snapshot?**
- The Medidata eTMF API provides **pre-generated Excel reports** rather than row-level APIs with cursors.
- Reports are generated by the eTMF system on a schedule and represent a full snapshot of the data at generation time.
- There is no `updatedAt` or cursor field at the row level within the Excel data.
- The `created_at_from` / `created_at_to` parameters on `/fetch_reports` filter **report generation time**, not individual record modification time.
- The current notebook implementation uses `TRUNCATE TABLE` + full overwrite, confirming snapshot behavior.

---

## **Read API for Data Retrieval**

Data retrieval from Medidata eTMF is a **two-step process**:

### Step 1: List Reports — `GET /fetch_reports`

**Base URL**: `https://api.mdsol.com/fetch_reports`

**Method**: `GET`

**Authentication**: MAuth request signing

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `client_division_scheme_uuid` | string (UUID) | ✅ Yes | Client division scheme identifier |
| `show_obsoleted` | boolean | No | Whether to include obsoleted reports. Default: `false` |
| `created_at_from` | integer (epoch ms) | No | Start of time window for report creation (inclusive). Epoch milliseconds. |
| `created_at_to` | integer (epoch ms) | No | End of time window for report creation (inclusive). Epoch milliseconds. |
| `pageSize` | integer | No | Number of records per page. Default/recommended: `1000` |
| `pageStart` | integer | No | Offset for pagination (0-based). Default: `0` |

#### Response Structure

```json
{
  "children": {
    "elements": [
      {
        "uuid": "067ef14b-114e-4e78-8962-867c25602d3f",
        "name": "StudyName_KPI Full Details",
        "systemFolderTypeLocalized": "eTMF Document Full Details",
        "updatedAt": "2025-12-01T10:30:00Z",
        "createdAt": "2025-12-01T10:00:00Z"
      }
    ],
    "hasNextPage": true
  }
}
```

#### Pagination

- **Type**: Offset-based pagination
- **Mechanism**: Increment `pageStart` by `pageSize` after each page
- **Termination**: Continue until `hasNextPage` is `false`
- **Page size**: Recommended `1000`

#### Example: Paginated Report Listing

```python
all_results = []
has_next_page = True
page_start = 0

while has_next_page:
    payload = {
        "client_division_scheme_uuid": client_division_scheme_uuid,
        "show_obsoleted": False,
        "created_at_from": start_ms,
        "created_at_to": end_ms,
        "pageSize": 1000,
        "pageStart": page_start
    }
    result = requests.get(url, auth=mauth, headers=headers, params=payload)
    if result.status_code == 200:
        data = result.json()
        all_results.extend(data['children']['elements'])
        has_next_page = data['children'].get('hasNextPage', False)
        page_start += payload['pageSize']
    else:
        print(f"Error: {result.status_code} - {result.text}")
        break
```

### Step 2: Download Report Content — `GET /regulated_files/{fsi_uuid}/content`

**Base URL**: `https://api.mdsol.com/regulated_files/{fsi_uuid}/content`

**Method**: `GET`

**Authentication**: MAuth request signing

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `fsi_uuid` | string (UUID) | ✅ Yes | The UUID of the report file (obtained from Step 1) |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `client_division_scheme_uuid` | string (UUID) | ✅ Yes | Client division scheme identifier |

#### Response

- **Content-Type**: Binary (Excel `.xlsx` file)
- **Status 200**: Returns the Excel file content as bytes
- **Status 404**: Report file not found
- **Status 502**: Internal server error (observed in testing — retry with backoff)

#### Example: Downloading and Parsing Report Content

```python
from io import BytesIO
import pandas as pd

url = f"https://api.mdsol.com/regulated_files/{fsi_uuid}/content"
payload = {'client_division_scheme_uuid': client_division_scheme_uuid}

result = requests.get(url, auth=mauth, headers=headers, params=payload)
if result.status_code == 200:
    df = pd.read_excel(BytesIO(result.content), dtype=str)
    print(f"Fetched {len(df)} rows, {df.shape[1]} columns")
else:
    print(f"Failed: {result.status_code} - {result.text}")
```

### Complete End-to-End Read Flow

```python
import re
import pandas as pd
from io import BytesIO

# Step 1: Fetch report listing
all_results = fetch_all_reports(mauth, headers, client_division_scheme_uuid, start_ms, end_ms)

if not all_results:
    # No reports found — truncate tables and exit
    for table in ["full_details", "filed_docs", "rejections"]:
        spark.sql(f"TRUNCATE TABLE lakehouse_production.0_iron.medidata_etmf_{table}_report")
    dbutils.notebook.exit("No results found")

# Step 2: Filter and group reports
fetch_reports_df = pd.DataFrame(all_results)
pattern = r'(All Studies_KPI Rejections|.*_KPI Full Details|.*_KPI Total Filed Docs)'
filtered = fetch_reports_df[fetch_reports_df['name'].str.contains(pattern, case=False, na=False, regex=True)]
filtered['matched_study'] = filtered['name'].str.extract(pattern, flags=re.IGNORECASE, expand=False)
filtered['updatedAt'] = pd.to_datetime(filtered['updatedAt'], errors='coerce')
filtered = filtered.sort_values(['matched_study', 'updatedAt'], ascending=[True, False])
latest_per_study = filtered.groupby('matched_study', as_index=False).first()

# Step 3: Extract UUIDs by report type
uuids_full_details = latest_per_study.loc[
    latest_per_study['systemFolderTypeLocalized'] == "eTMF Document Full Details", 'uuid'
].tolist()
uuids_filed_docs = latest_per_study.loc[
    latest_per_study['systemFolderTypeLocalized'] == "eTMF Filed Documents", 'uuid'
].tolist()
uuids_rejections = latest_per_study.loc[
    latest_per_study['systemFolderTypeLocalized'] == "Rejections", 'uuid'
].tolist()

# Step 4: Download and parse each report
for uuid in uuids_full_details:
    url = f"https://api.mdsol.com/regulated_files/{uuid}/content"
    result = requests.get(url, auth=mauth, headers=headers,
                         params={'client_division_scheme_uuid': client_division_scheme_uuid})
    if result.status_code == 200:
        df = pd.read_excel(BytesIO(result.content), dtype=str)
        df['uuid'] = uuid
        # Process and save...
```

### Rate Limits

- **No documented rate limits** in the Medidata eTMF API. However:
  - The API uses CloudFront CDN (observed in response headers), which may impose connection limits.
  - Status `502` errors have been observed (Internal Server Error via API Gateway), suggesting backend capacity limits.
  - **Recommendation**: Implement exponential backoff for `429`, `500`, `502`, `503` status codes.
  - The existing notebook processes reports sequentially (no concurrency on report downloads), which is a safe default.

### Error Handling

| Status Code | Meaning | Action |
|-------------|---------|--------|
| `200` | Success | Process response |
| `404` | Report not found | Skip — report may have been deleted or is unavailable |
| `429` | Rate limit exceeded | Retry with exponential backoff |
| `500` | Internal server error | Retry with exponential backoff |
| `502` | Bad Gateway (API Gateway error) | Retry with exponential backoff |
| `503` | Service unavailable | Retry with exponential backoff |

---

## **Field Type Mapping**

All data from Medidata eTMF reports is returned as **Excel files**. During ingestion, all columns are read as `string` type (`dtype=str` in `pd.read_excel`). Type conversion is applied downstream.

### Raw API → Spark Mapping

| Excel/API Field Type | Pandas Read Type | Spark Data Type | Notes |
|---------------------|------------------|-----------------|-------|
| All fields | `string` (forced via `dtype=str`) | `StringType` | All columns ingested as strings in the iron (raw) layer |

### Downstream Type Conversions (Bronze Layer)

Date/time fields require parsing from Medidata-specific formats:

| Field | Raw Format | Target Type | Parsing Pattern |
|-------|-----------|-------------|-----------------|
| `created_at` (Created On Date/Time) | `ddMMMyyyy HH:mm:ss GMT` | `TimestampType` | `regexp_replace(value, 'GMT', ''), 'ddMMMyyyy HH:mm:ss'` |
| `edit_completed_rejected_by` (when timestamp) | `username, ddMMMyyyy HH:mm:ss GMT` | `TimestampType` | Extract after comma: `split(value, ',')[1]`, then parse with `' ddMMMyyyy HH:mm:ss'` |
| `document_date` | `ddMMMyyyy` | `DateType` | `to_date(value, 'ddMMMyyyy')` |
| `rejected_date` | `TBD:` Varies | `DateType` or `TimestampType` | Format needs verification from actual data |
| `created_on` (Filed Docs) | `TBD:` Varies | `TimestampType` | Format needs verification from actual data |
| `updated_on` (Filed Docs) | `TBD:` Varies | `TimestampType` | Format needs verification from actual data |

### Date Format Note

Medidata uses a **non-standard date format**: `ddMMMyyyy` (e.g., `01Jan2025`). The month abbreviation is a 3-letter English month name. Timezone is always `GMT` when present.

---

## **Sources and References**

### Research Log

| Source Type | URL/Location | Accessed (UTC) | Confidence | What it confirmed |
|-------------|-------------|----------------|------------|-------------------|
| Internal Notebook (Production) | `/Repos/Development/Databricks-2.0/Ingestion/ELs/Sources/Medidata : eTMF/el_main` (ID: 3800064374765738) | 2026-03-30 | Highest | Full end-to-end ingestion flow: MAuth auth, fetch_reports endpoint, regulated_files endpoint, pagination, report filtering, column mapping, table schemas |
| Internal Notebook (API Testing) | `/Repos/Development/Databricks-2.0/Ingestion/ELs/Sources/Medidata : CTMS/Medidata eTMF API testing.ipynb` (ID: 790276021761828) | 2026-03-30 | Highest | Additional endpoint testing, raw column counts (~123 for full details, ~781K rows), date parsing patterns, QC fields |
| Internal Notebook (CTMS) | `/Repos/Development/Databricks-2.0/Ingestion/ELs/Sources/Medidata : CTMS/el_main` (ID: 1877199210403973) | 2026-03-30 | High | Shared MAuth authentication pattern, secret scope structure, API version header |
| Lakehouse Table Schema | `lakehouse_production.0_iron.medidata_etmf_full_details_report` | 2026-03-30 | Highest | 18 columns: document_id, fsi_uuid, level, study, environment, site, folder_path, zone, artifact, name, version, state, wf_type, initiator, created_by, edit_completed_rejected_by, created_at, document_date |
| Lakehouse Table Schema | `lakehouse_production.0_iron.medidata_etmf_filed_docs_report` | 2026-03-30 | Highest | 15 columns: document_name, folder_path, study, country, site, zone, section, artifact_#, format, created_on, created_by, document_title, version, updated_on, uuid |
| Lakehouse Table Schema | `lakehouse_production.0_iron.medidata_etmf_rejections_report` | 2026-03-30 | Highest | 14 columns: document_name, folder_path, rejected_date, rejected_by, rejection_reason, comment, open, finalized_version, finalized_document_state, owner, version, study, site, uuid |
| Medidata MAuth Client | PyPI: `mauth-client` package | 2026-03-30 | High | Python MAuth implementation for request signing |

### Notes

- **No public API documentation found**: Medidata's eTMF API documentation is not publicly available. All endpoint details were reverse-engineered from the existing production notebooks.
- **No third-party connectors**: No Airbyte, Singer/Meltano, Fivetran, or dltHub connectors exist for Medidata eTMF. This is a proprietary clinical trial management system with private APIs.
- **API base URL**: `https://api.mdsol.com` — this is Medidata Solutions' (now part of Dassault Systèmes) API gateway.

### Known Quirks

1. **Report-based extraction**: Unlike typical REST APIs with CRUD endpoints per object, Medidata eTMF provides pre-generated Excel reports. The connector must discover reports, filter by type, and download/parse Excel files.
2. **Time parameters in epoch milliseconds**: The `created_at_from` and `created_at_to` parameters use epoch milliseconds (not seconds or ISO format).
3. **Excel binary responses**: The `/regulated_files/{uuid}/content` endpoint returns binary Excel data, not JSON. The `openpyxl` library is required for parsing.
4. **Multiple reports per study**: Each study may generate multiple versions of the same report type. The ingestion process must select the **latest version** by `updatedAt` to avoid duplicates.
5. **No incremental support**: There is no row-level cursor or change tracking. Full snapshot refresh is the only viable strategy.
6. **Date format**: Medidata uses `ddMMMyyyy` format (e.g., `01Jan2025`) which is non-standard and requires custom parsing.
7. **502 errors observed**: The API Gateway (CloudFront-backed) may return 502 errors under load. Implement retry logic.
8. **Timezone handling**: The production notebook uses `Australia/ACT` timezone for generating the time window parameters. Ensure timezone consistency in the connector.

### Deferred Items / TBD

- `TBD:` Exact date formats for `rejected_date`, `created_on`, and `updated_on` fields in Filed Docs and Rejections reports — need to verify from actual data samples.
- `TBD:` Whether the `system_folder_report_type` parameter (e.g., `ETMF_DOCUMENT_DETAIL_REPORT`) can be used to filter reports by type directly in the `/fetch_reports` call (commented out in current notebook).
- `TBD:` Full list of possible values for `State` field (observed: `ACCEPTED`, `PENDING`, `REJECTED`).
- `TBD:` Full list of possible values for `WF Type` field (observed: `File Document to TMF`, `Standard Workflow`).
- `TBD:` Whether there are additional report types beyond the three currently ingested.
- `TBD:` Rate limit details — no official documentation available; observed 502 errors suggest some form of throttling.
