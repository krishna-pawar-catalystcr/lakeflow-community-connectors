# Lakeflow SurveySparrow Community Connector

This documentation describes how to configure and use the **SurveySparrow** Lakeflow community connector to ingest survey, response, contact, and operational data from the SurveySparrow V3 API into Databricks.


## Prerequisites

- **SurveySparrow account**: An account with sufficient permissions to access the objects you want to ingest.
- **Personal Access Token**: Generated via a Private App in the SurveySparrow developer settings (see [Obtaining the Access Token](#obtaining-the-access-token) below). The token must have read access to the resources you plan to sync.
- **Network access**: The Databricks environment must be able to reach the SurveySparrow API endpoint for your region (e.g., `https://eu-api.surveysparrow.com/v3` for EU accounts).
- **Lakeflow / Databricks environment**: A workspace where you can register a Lakeflow community connector and run ingestion pipelines.


## Setup

### Required Connection Parameters

Provide the following **connection-level** options when configuring the connector:

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `access_token` | string | yes | SurveySparrow Personal Access Token for API authentication. | `pr0j9Yari5WK...` |
| `region` | string | no | Data center region for your SurveySparrow account. Accepted values: `us` (default), `eu`, `ap`, `me`, `uk`, `ap-sy`, `ca`. | `eu` |
| `externalOptionsAllowList` | string | yes | Comma-separated list of table-specific option names allowed to be passed to the connector. The full, definitive list of supported values is: `survey_id,max_records_per_batch,window_seconds,limit` | `survey_id,max_records_per_batch,window_seconds,limit` |

> **Note**: Table-specific options such as `survey_id`, `max_records_per_batch`, `window_seconds`, and `limit` are **not** connection parameters. They are per-table options set in the pipeline specification. Their names must appear in `externalOptionsAllowList` for the connection to permit them.


### Obtaining the Access Token

SurveySparrow uses Bearer token authentication via **Private Apps**:

1. Log in to SurveySparrow.
2. Navigate to **Settings → Apps & Integrations → Private Apps**.
3. Click **Create Private App** (or open an existing one).
4. Copy the **Access Token** shown on the app page. The token is displayed once — store it securely.
5. Confirm which **region** your account belongs to (visible in the account URL or via SurveySparrow support). Use the corresponding region code when configuring the connector.

| Region | Code | API Base URL |
|---|---|---|
| United States (default) | `us` | `https://api.surveysparrow.com/v3` |
| Europe | `eu` | `https://eu-api.surveysparrow.com/v3` |
| Asia Pacific | `ap` | `https://ap-api.surveysparrow.com/v3` |
| Middle East | `me` | `https://me-api.surveysparrow.com/v3` |
| United Kingdom | `uk` | `https://eu-ln-api.surveysparrow.com/v3` |
| Asia Pacific (Sydney) | `ap-sy` | `https://ap-sy-api.surveysparrow.com/v3` |
| Canada | `ca` | `https://ca-api.surveysparrow.com/v3` |


### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways via the UI:

1. Follow the **Lakeflow Community Connector** UI flow from the **Add Data** page.
2. Select any existing Lakeflow Community Connector connection for this source or create a new one.
3. Set `externalOptionsAllowList` to `survey_id,max_records_per_batch,window_seconds,limit`. This is required to pass per-table options for survey-partitioned tables and to allow incremental tuning options.

The connection can also be created using the standard Unity Catalog API.


## Supported Objects

The SurveySparrow connector exposes a static list of **16 tables**:

- `surveys`
- `responses`
- `questions`
- `contacts`
- `contact_lists`
- `contact_properties`
- `users`
- `roles`
- `teams`
- `survey_folders`
- `channels`
- `variables`
- `tickets`
- `audit_logs`
- `webhooks`
- `targets`


### Object Summary, Primary Keys, and Ingestion Mode

| Table | Description | Ingestion Type | Primary Key | Incremental Cursor |
|---|---|---|---|---|
| `surveys` | Survey metadata and configuration | `cdc` | `id` | `updated_at` |
| `responses` | Individual survey responses with answers | `cdc` | `id` | `completed_time` |
| `questions` | Questions belonging to a survey | `snapshot` | `id` | N/A |
| `contacts` | Contact records in the account | `cdc` | `id` | `createddate` |
| `contact_lists` | Contact list metadata | `snapshot` | `id` | N/A |
| `contact_properties` | Custom contact property definitions | `snapshot` | `id` | N/A |
| `users` | Account user records | `snapshot` | `id` | N/A |
| `roles` | Roles defined in the account | `snapshot` | `id` | N/A |
| `teams` | Teams defined in the account | `snapshot` | `id` | N/A |
| `survey_folders` | Folder structure for organising surveys | `snapshot` | `id` | N/A |
| `channels` | Distribution channels for a survey | `snapshot` | `id` | N/A |
| `variables` | Custom variables defined in a survey | `snapshot` | `id` | N/A |
| `tickets` | Support tickets | `cdc` | `id` | `updated_at` |
| `audit_logs` | Account-level audit log entries | `append` | `id` | `time` |
| `webhooks` | Configured webhooks | `snapshot` | `id` | N/A |
| `targets` | Configured targets (no stable primary key) | `snapshot` | N/A | N/A |


### Survey-Partitioned Tables

Four tables require a parent survey to be identified: `responses`, `questions`, `channels`, and `variables`. When `survey_id` is provided as a table option, data is fetched only for that survey. When omitted, the connector automatically lists all surveys first and then fetches child records for each one, combining the results. A `survey_id` column is added to every output record.


### Schema Highlights

- **`responses`**: The `answers`, `channel`, `contact`, and `expressions` fields are stored as JSON strings. Parse them with `from_json()` or `json_tuple()` downstream if you need structured access.
- **`questions`**: The `properties`, `choices`, and `annotations` fields are JSON strings representing the API objects.
- **`tickets`**: The `requester`, `priority`, `status`, `custom_fields`, `source`, `agent`, and `team` fields are stored as JSON strings.
- **`audit_logs`**: The `actor` field is a JSON string. The `id` field is a UUID string (not a numeric integer). This table is append-only — records are never updated or deleted.
- **`survey_folders`**: The `teams`, `users`, `surveys`, `subfolders`, and `echoes` fields are stored as JSON strings.
- **`targets`**: The `targets` field is a JSON array string; `page` and `count` are integers. This table has no stable primary key.


## Table Configurations

### Source & Destination

These are set directly under each `table` object in the pipeline spec:

| Option | Required | Description |
|---|---|---|
| `source_table` | Yes | Table name in the source system |
| `destination_catalog` | No | Target catalog (defaults to pipeline's default) |
| `destination_schema` | No | Target schema (defaults to pipeline's default) |
| `destination_table` | No | Target table name (defaults to `source_table`) |


### Common `table_configuration` Options

These are set inside the `table_configuration` map:

| Option | Required | Description |
|---|---|---|
| `scd_type` | No | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. Applicable to CDC and snapshot tables; not supported for `audit_logs`. |
| `primary_keys` | No | List of columns to override the connector's default primary keys. |
| `sequence_by` | No | Column used to order records for SCD Type 2 change tracking. |


### Source-Specific `table_configuration` Options

| Table | Option | Required | Default | Description |
|---|---|---|---|---|
| `responses`, `questions`, `channels`, `variables` | `survey_id` | No | (all surveys) | Restrict ingestion to a single survey. If omitted, all surveys are iterated automatically. |
| `surveys`, `responses`, `contacts`, `tickets` | `max_records_per_batch` | No | `200` | Maximum records returned per microbatch. Reduce for large accounts or to avoid rate limits. |
| `surveys`, `responses`, `contacts`, `tickets` | `window_seconds` | No | `3600` | Width of the incremental time window in seconds. Reduce for high-volume accounts; increase when the default window is too narrow to make progress. |
| `audit_logs` | `max_records_per_batch` | No | `200` | Maximum records per microbatch for the append-only audit log. |
| `audit_logs` | `limit` | No | `100` | API page size for audit log requests (max 500). Keep small to bound each API call. |


## Data Type Mapping

SurveySparrow JSON fields are mapped to Spark types as follows:

| SurveySparrow JSON Type | Example Fields | Spark Type | Notes |
|---|---|---|---|
| integer | `id`, `survey_folder_id`, `role_id`, `contact_id` | `LongType` | All integers stored as 64-bit to avoid overflow. |
| string | `name`, `email`, `status`, `type`, `language` | `StringType` | Identifiers and text fields. |
| boolean | `archived`, `active`, `admin`, `owner`, `verified`, `is_required` | `BooleanType` | Standard `true`/`false` values. |
| ISO 8601 datetime | `created_at`, `updated_at`, `completed_time`, `time` | `StringType` | Stored as UTC strings; cast to `TIMESTAMP` downstream as needed. |
| object / array | `answers`, `properties`, `choices`, `actor`, `requester`, `teams` | `StringType` (JSON) | Complex fields are serialised to JSON strings. Use `from_json()` to parse. |
| UUID string | `audit_logs.id` | `StringType` | UUID primary key, not a numeric integer. |


## How to Run

### Step 1: Clone/Copy the Source Connector Code

Follow the Lakeflow Community Connector UI, which will guide you through setting up a pipeline using the selected source connector code.


### Step 2: Configure Your Pipeline

1. Update the `pipeline_spec` in the main pipeline file (e.g., `ingest.py`).
2. For survey-partitioned tables, optionally specify a `survey_id` to restrict ingestion to a single survey. For incremental tables, tune `max_records_per_batch` and `window_seconds` to match your account's data volume.

```json
{
  "pipeline_spec": {
    "connection_name": "<your_surveysparrow_connection>",
    "objects": [
      {
        "table": {
          "source_table": "surveys",
          "table_configuration": {
            "max_records_per_batch": "500",
            "window_seconds": "3600"
          }
        }
      },
      {
        "table": {
          "source_table": "responses",
          "table_configuration": {
            "survey_id": "<your_survey_id>",
            "max_records_per_batch": "200",
            "window_seconds": "3600"
          }
        }
      },
      {
        "table": {
          "source_table": "questions",
          "table_configuration": {
            "survey_id": "<your_survey_id>"
          }
        }
      },
      {
        "table": {
          "source_table": "audit_logs",
          "table_configuration": {
            "limit": "100",
            "max_records_per_batch": "500"
          }
        }
      },
      {
        "table": {
          "source_table": "contacts"
        }
      }
    ]
  }
}
```

3. (Optional) Customise the source connector code if needed for special use cases.


### Step 3: Run and Schedule the Pipeline

#### Best Practices

- **Start small**: Begin by syncing a small set of tables (e.g., `surveys`, `users`) to validate your connection before enabling all 16 tables.
- **Tune batch sizes for large accounts**: If your account has hundreds of surveys or thousands of responses, reduce `max_records_per_batch` and `window_seconds` to keep individual API calls fast and avoid timeouts.
- **Omit `survey_id` for full syncs**: For `responses`, `questions`, `channels`, and `variables`, omitting `survey_id` causes the connector to iterate over all surveys automatically — useful for initial loads, but slower for large accounts. Provide an explicit `survey_id` for faster, scoped syncs.
- **`audit_logs` is append-only**: Do not configure `SCD_TYPE_2` for `audit_logs`. Records are inserted once and never updated.
- **API rate limits**: SurveySparrow enforces API rate limits. If you encounter `429 Too Many Requests`, reduce the pipeline trigger frequency or lower `max_records_per_batch`.

#### Troubleshooting

**Common Issues:**

- **401 Unauthorized**: The `access_token` is invalid, expired, or was generated for a different region. Regenerate the token via **Settings → Apps & Integrations → Private Apps** and verify the `region` parameter matches your account's data centre.
- **Empty results for `responses`, `questions`, `channels`, or `variables`**: These tables require a valid survey to exist in the account. When `survey_id` is omitted, results depend on surveys being present. Verify with the SurveySparrow UI.
- **Slow initial sync on large accounts**: The auto-discovery of all survey IDs for survey-partitioned tables adds extra API calls. Provide explicit `survey_id` values to speed up the first run.
- **Incremental sync not progressing**: If `window_seconds` is very small and the account has sparse data, the cursor advances through many empty windows. Increase `window_seconds` to cover a wider time range per microbatch.
- **`targets` table has no primary key**: The `targets` table does not expose a stable record identifier. Avoid configuring primary-key-dependent SCD modes for this table.


## References

- [SurveySparrow API V3 Documentation](https://developers.surveysparrow.com/rest-apis)
- [SurveySparrow Private Apps (Authentication)](https://developers.surveysparrow.com/rest-apis#section/Authentication)
- [Lakeflow Community Connectors GitHub](https://github.com/databrickslabs/lakeflow-community-connectors)
- [Databricks Lakeflow Documentation](https://docs.databricks.com/en/ingestion/lakeflow-connect/index.html)
