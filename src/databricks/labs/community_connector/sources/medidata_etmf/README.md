# Lakeflow Medidata eTMF Community Connector

This documentation provides setup instructions and reference information for the Medidata eTMF source connector.

The Lakeflow Medidata eTMF Connector allows you to extract electronic Trial Master File (eTMF) data from Medidata's clinical trial management platform and load it into your data lake. This connector retrieves pre-generated KPI reports covering document details, filed documents, and rejection records across all clinical studies.

## Prerequisites

- Access to a Medidata eTMF instance with API permissions
- A registered MAuth application with a valid UUID and RSA private key
- A client division scheme UUID identifying your organization scope
- The `mauth-client` Python package (automatically included in the connector)

## Setup

### Required Connection Parameters

To configure the connector, provide the following parameters in your connector options:

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `app_uuid` | string | Yes | Application UUID registered in Medidata's MAuth system | `40b93548-b79f-4ac0-82ec-005d965e21b5` |
| `private_key` | string | Yes | RSA private key in PEM format used to sign API requests | `-----BEGIN RSA PRIVATE KEY-----\nMIIEp...` |
| `client_division_scheme_uuid` | string | Yes | Client division scheme UUID identifying your organization | `2bb466e6-e8bb-475f-b6a0-a25c89034052` |
| `base_url` | string | No | Base URL for the Medidata API (defaults to `https://api.mdsol.com`) | `https://api.mdsol.com` |

Since this connector uses table-specific options for time window filtering, the `externalOptionsAllowList` connection option is **required** and must be set to:

```
created_at_from,created_at_to
```

### Obtaining Your Credentials

1. **Application UUID (`app_uuid`)**: Contact your Medidata administrator or Medidata Support to register a new MAuth application. You will receive a UUID that identifies your application.
2. **RSA Private Key (`private_key`)**: When your MAuth application is registered, an RSA key pair is generated. Store the private key securely. The connector expects the full PEM content (not a file path).
3. **Client Division Scheme UUID (`client_division_scheme_uuid`)**: This UUID is provided by your Medidata administrator and identifies your organization's data scope within the eTMF system.

### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways via the UI:
1. Follow the Lakeflow Community Connector UI flow from the "Add Data" page
2. Select any existing Lakeflow Community Connector connection for this source or create a new one.
3. Set the `externalOptionsAllowList` parameter to `created_at_from,created_at_to` to allow time window configuration per table.

The connection can also be created using the standard Unity Catalog API.


## Supported Objects

The Medidata eTMF connector supports three report-based objects. All objects use **snapshot** ingestion (full refresh on each run).

### etmf_full_details
- **Primary Keys**: `document_id`, `fsi_uuid`
- **Ingestion Strategy**: Snapshot (full refresh)
- **Description**: Comprehensive document-level details from eTMF KPI Full Details reports. Includes document state, workflow type, folder path, zone classification, and timestamps for all documents across clinical studies.
- **Key Fields**: `document_id`, `fsi_uuid`, `study`, `environment`, `site`, `folder_path`, `zone`, `artifact`, `name`, `version`, `state`, `wf_type`, `initiator`, `created_by`, `edit_completed_rejected_by`, `created_at`, `document_date`

### etmf_filed_docs
- **Primary Keys**: `document_name`, `folder_path`, `study`, `uuid`
- **Ingestion Strategy**: Snapshot (full refresh)
- **Description**: Summary of filed and finalized documents from eTMF KPI Total Filed Docs reports. Covers document metadata, folder hierarchy, zone and section classification, and creation details.
- **Key Fields**: `document_name`, `folder_path`, `study`, `country`, `site`, `zone`, `section`, `artifact_#`, `format`, `created_on`, `created_by`, `document_title`, `version`, `updated_on`, `uuid`

### etmf_rejections
- **Primary Keys**: `document_name`, `folder_path`, `rejected_date`, `uuid`
- **Ingestion Strategy**: Snapshot (full refresh)
- **Description**: Document rejection records from eTMF KPI Rejections reports. Tracks rejection reasons, reviewers, and the finalization state of rejected documents.
- **Key Fields**: `document_name`, `folder_path`, `rejected_date`, `rejected_by`, `rejection_reason`, `comment`, `open`, `finalized_version`, `finalized_document_state`, `owner`, `version`, `study`, `site`, `uuid`


## Table Configurations

### Source & Destination

These are set directly under each `table` object in the pipeline spec:

| Option | Required | Description |
|---|---|---|
| `source_table` | Yes | One of: `etmf_full_details`, `etmf_filed_docs`, `etmf_rejections` |
| `destination_catalog` | No | Target catalog (defaults to pipeline's default) |
| `destination_schema` | No | Target schema (defaults to pipeline's default) |
| `destination_table` | No | Target table name (defaults to `source_table`) |

### Common `table_configuration` options

These are set inside the `table_configuration` map alongside any source-specific options:

| Option | Required | Description |
|---|---|---|
| `scd_type` | No | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. Applicable to SNAPSHOT ingestion mode. |
| `primary_keys` | No | List of columns to override the connector's default primary keys |
| `sequence_by` | No | Column used to order records for SCD Type 2 change tracking |

### Special `table_configuration` options

The Medidata eTMF connector supports time window filtering to control which reports are fetched:

| Option | Required | Description |
|---|---|---|
| `created_at_from` | No | Start of report creation time window in epoch milliseconds. Defaults to the first day of the current month at 00:00:00 UTC. |
| `created_at_to` | No | End of report creation time window in epoch milliseconds. Defaults to the first day of the current month at 23:59:59 UTC. |

These options filter the **report generation date**, not individual record timestamps. They control which set of pre-generated eTMF reports are downloaded from the Medidata API.

**Example**: To fetch reports generated on January 1, 2026:
```
"created_at_from": "1767225600000"
"created_at_to": "1767311999000"
```


## Data Type Mapping

All data from Medidata eTMF reports is ingested as string type. Date and timestamp fields use Medidata-specific formats that can be parsed downstream.

| Source Format | Databricks Type | Notes |
|---------------|-----------------|-------|
| All fields | STRING | All columns from Excel reports are read as strings |

### Date Format Reference

The following date formats are used in Medidata eTMF fields and can be parsed in downstream transformations:

| Field | Format | Example |
|-------|--------|---------|
| `created_at` | `ddMMMyyyy HH:mm:ssGMT` | `08Jul2025 19:58:42GMT` |
| `edit_completed_rejected_by` | `username, ddMMMyyyy HH:mm:ss GMT` | `John Smith, 15Jan2026 10:30:00 GMT` |
| `document_date` | `ddMMMyyyy` | `01Jan2025` |
| `created_on` (filed docs) | `ddMMMyyyy HH:mm:ss GMT+0000` | `04Mar2025 18:02:51 GMT+0000` |
| `updated_on` (filed docs) | `ddMMMyyyy HH:mm:ss GMT+0000` | `04Mar2025 18:02:51 GMT+0000` |
| `rejected_date` | `ddMMMyyyy HH:mm:ss GMT+0000` | `19Oct2022 17:23:34 GMT+0000` |


## How to Run

### Step 1: Clone/Copy the Source Connector Code
Follow the Lakeflow Community Connector UI, which will guide you through setting up a pipeline using the selected source connector code.

### Step 2: Configure Your Pipeline
1. Update the `pipeline_spec` in the main pipeline file (e.g., `ingest.py`).
2. Configure each table with optional time window parameters to control which reports are fetched:

```json
{
  "pipeline_spec": {
      "connection_name": "medidata_etmf_connection",
      "object": [
        {
            "table": {
                "source_table": "etmf_full_details",
                "table_configuration": {
                    "created_at_from": "1767225600000",
                    "created_at_to": "1767311999000"
                }
            }
        },
        {
            "table": {
                "source_table": "etmf_filed_docs",
                "table_configuration": {
                    "created_at_from": "1767225600000",
                    "created_at_to": "1767311999000"
                }
            }
        },
        {
            "table": {
                "source_table": "etmf_rejections",
                "table_configuration": {
                    "created_at_from": "1767225600000",
                    "created_at_to": "1767311999000"
                }
            }
        }
      ]
  }
}
```
3. (Optional) Customize the source connector code if needed for special use cases.

### Step 3: Run and Schedule the Pipeline

#### Best Practices

- **Start Small**: Begin by syncing one table (e.g., `etmf_rejections` which is typically the smallest) to test your pipeline configuration.
- **Use Narrow Time Windows**: Always specify `created_at_from` and `created_at_to` to scope the report fetch. Without time filtering, the API defaults to the first day of the current month.
- **Schedule Monthly**: Since reports are generated periodically in the eTMF system, a monthly sync schedule aligned with report generation is recommended.
- **Monitor API Responses**: The Medidata API may return HTTP 408 (timeout) or 502 (gateway error) for very broad queries. The connector retries these automatically with exponential backoff.

#### Troubleshooting

**Common Issues:**

- **HTTP 408 (Request Timeout)**: The time window is too broad, causing the API to scan too many reports. Narrow the `created_at_from` / `created_at_to` range to a single day.
- **HTTP 502 (Bad Gateway)**: Transient API gateway error. The connector retries automatically up to 5 times with exponential backoff.
- **Empty Results**: No KPI reports matching the expected patterns (`*_KPI Full Details`, `*_KPI Total Filed Docs`, `All Studies_KPI Rejections`) were generated within the specified time window. Verify the time window corresponds to when reports are generated in your eTMF instance.
- **Authentication Errors**: Verify that your `app_uuid` is registered, the `private_key` is the correct RSA PEM content (not a file path), and `client_division_scheme_uuid` matches your organization.


## References

- [Medidata Solutions](https://www.medidata.com/) — Medidata (Dassault Systèmes) clinical technology platform
- [mauth-client Python Package](https://pypi.org/project/mauth-client/) — MAuth authentication library used for API request signing
- Medidata eTMF API documentation is not publicly available; consult your Medidata administrator for endpoint details
