# **SurveySparrow API Documentation**

## **Authorization**

- **Chosen method**: Bearer Token (Personal Access Token via Private App)
- **Alternative**: OAuth 2.0 Authorization Code flow (see Known Quirks)
- **Auth placement**: HTTP header — `Authorization: Bearer <access_token>`
- **Alternative placement**: Query parameter — `?access_token=<token>`

**Token acquisition** (performed outside the connector, one-time setup):
1. Log in to SurveySparrow → Settings → Apps & Integrations
2. Create a **Private App**, enter Name and Description, select required scopes
3. Generate the access token — **copy it immediately** (displayed only once)
4. Store the token securely; re-generate if lost

**OAuth note**: The connector **stores** the `access_token` directly (or for OAuth flow: `client_id`, `client_secret`, `refresh_token`) and exchanges the refresh token for a new access token at runtime. The connector **does not** run user-facing OAuth flows.

**OAuth 2.0 token URL** (if refresh-token flow is needed):

| Region | Token URL |
|--------|----------|
| US | `https://api.surveysparrow.com/o/oauth/token` |
| EU | `https://eu-api.surveysparrow.com/o/oauth/token` |
| AP | `https://ap-api.surveysparrow.com/o/oauth/token` |
| ME | `https://me-api.surveysparrow.com/o/oauth/token` |
| UK | `https://eu-ln-api.surveysparrow.com/o/oauth/token` |
| AP-SY | `https://ap-sy-api.surveysparrow.com/o/oauth/token` |
| CA | `https://ca-api.surveysparrow.com/o/oauth/token` |

**Refresh token request body**:
```json
{
  "client_id": "{client_id}",
  "client_secret": "{client_secret}",
  "grant_type": "refresh_token",
  "refresh_token": "{refresh_token}"
}
```

**Example authenticated request**:
```bash
curl --request GET \
  --url https://api.surveysparrow.com/v3/surveys \
  --header 'Authorization: Bearer your-surveysparrow-access-token'
```

**Base URLs by region** (all API calls use `/v3/` prefix):

| Region | Base URL |
|--------|----------|
| United States (US) | `https://api.surveysparrow.com/v3` |
| Europe (EU) | `https://eu-api.surveysparrow.com/v3` |
| Asia/Pacific (AP) | `https://ap-api.surveysparrow.com/v3` |
| Middle East (ME) | `https://me-api.surveysparrow.com/v3` |
| United Kingdom (UK) | `https://eu-ln-api.surveysparrow.com/v3` |
| Sydney (AP-SY) | `https://ap-sy-api.surveysparrow.com/v3` |
| Canada (CA) | `https://ca-api.surveysparrow.com/v3` |

Contact SurveySparrow support to confirm your account's data center region.


## **Object List**

The object list is **static** — defined by the connector, not discoverable via an API endpoint. All listed objects correspond to V3 REST resources.

| Object Name | API Endpoint | Description | Parent Object | Ingestion Type |
|-------------|-------------|-------------|---------------|----------------|
| `surveys` | `GET /v3/surveys` | Survey metadata and configuration | None | `cdc` |
| `responses` | `GET /v3/responses` | Individual survey responses | `surveys` (survey_id required) | `cdc` |
| `questions` | `GET /v3/questions` | Questions within a survey | `surveys` (survey_id required) | `snapshot` |
| `contacts` | `GET /v3/contacts` | Contact records | None | `cdc` |
| `contact_lists` | `GET /v3/contact_lists` | Contact list metadata | None | `snapshot` |
| `contact_properties` | `GET /v3/contact_properties` | Custom contact property definitions | None | `snapshot` |
| `users` | `GET /v3/users` | Account users | None | `snapshot` |
| `roles` | `GET /v3/roles` | User roles | None | `snapshot` |
| `teams` | `GET /v3/teams` | Teams (survey or ticket) | None | `snapshot` |
| `survey_folders` | `GET /v3/survey_folders` | Survey folder/workspace metadata | None | `snapshot` |
| `channels` | `GET /v3/channels` | Survey distribution channels/shares | `surveys` (survey_id required) | `snapshot` |
| `variables` | `GET /v3/variables` | Custom survey variables | `surveys` (survey_id required) | `snapshot` |
| `tickets` | `GET /v3/tickets` | Support tickets | None | `cdc` |
| `audit_logs` | `GET /v3/audit_logs` | Account audit log events | None | `append` |
| `webhooks` | `GET /v3/webhooks` | Webhook configurations | None | `snapshot` |
| `targets` | `GET /v3/targets` | Survey targets | None | `snapshot` |

**Object hierarchy notes**:
- `responses`, `questions`, `channels`, and `variables` are children of `surveys` — each request requires a `survey_id` parameter. The connector iterates over a user-provided list of survey IDs.
- `contacts` can optionally be filtered by `contact_list_id`.


## **Object Schema**

Schemas are **static** (no schema-discovery API). All fields documented below are from official API docs and verified against the Airbyte OSS implementation.

### `surveys`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Survey ID |
| `name` | string | Survey name |
| `archived` | boolean | Whether survey is archived |
| `survey_type` | string | Enum: `Conversational`, `ClassicForm`, `Kiosk`, `OfflineApp`, `NPS`, `NPSChat`, `CES`, `CESChat`, `CSAT`, `CSATChat`, `Employee360` |
| `created_at` | date-time | Creation timestamp |
| `updated_at` | date-time | Last update timestamp |
| `survey_folder_id` | integer | ID of the containing folder |
| `survey_folder_name` | string | Name of the containing folder |

### `responses`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Response ID |
| `survey_id` | integer | Parent survey ID |
| `contact_id` | integer | Associated contact ID (0 if anonymous) |
| `completed` | string | Submission status |
| `channel_id` | integer | Channel through which response was submitted |
| `language` | string | Response language (e.g., `en`) |
| `completed_time` | date-time | Timestamp when response was completed |
| `answers` | array | Array of answer objects: `{question, question_tags, question_id, skipped}` |
| `channel` | object | Channel info: `{name, type, status}` |
| `contact` | string/object | Contact information of the respondent |
| `expressions` | array | Sentiment/expression data |

### `questions`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Question ID |
| `type` | string | Question type (e.g., `TextInput`, `MultipleChoice`, `Rating`, `NPS`) |
| `position` | string | Order position within the survey (decimal string) |
| `hasDisplayLogic` | boolean | Whether display logic is applied |
| `properties` | object | Additional question properties (e.g., text, choices) |
| `survey_id` | integer | Parent survey ID |
| `section_id` | integer | Section/page ID within survey |
| `account_id` | integer | Account ID |
| `parent_question_id` | integer | Parent question ID for sub-questions |
| `choices` | array | Available answer choices |
| `annotations` | array | Additional annotations |
| `created_at` | date-time | Creation timestamp |
| `is_required` | boolean | Whether question is required |
| `multiple_answers` | boolean | Whether multiple answers are allowed |

### `contacts`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Contact ID |
| `active` | boolean | Whether contact is active |
| `email` | string | Email address |
| `first_name` | string | First name |
| `last_name` | string | Last name |
| `name` | string | Full name |
| `job_title` | string | Job title |
| `mobile` | string | Mobile phone number |
| `unsubscribed` | boolean | Whether contact has unsubscribed |
| `createddate` | string | Creation date (ISO string) |

### `contact_lists`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Contact list ID |
| `name` | string | List name |
| `description` | string | List description |
| `created_at` | date-time | Creation timestamp |

### `contact_properties`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Property ID |
| `name` | string | Property key name |
| `label` | string | Display label |
| `type` | string | Data type (e.g., `DATE`, `TEXT`, `NUMBER`) |
| `description` | string | Description |
| `contact_property_group_id` | integer | ID of the property group |
| `group` | string | Name of the property group |

### `users`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | User ID |
| `name` | string | Full name |
| `email` | string | Email address |
| `phone` | string | Phone number |
| `admin` | boolean | Is account admin |
| `owner` | boolean | Is account owner |
| `agency_owner` | boolean | Is agency owner |
| `verified` | boolean | Is account verified |
| `role_id` | integer | Assigned role ID |
| `created_at` | date-time | Account creation timestamp |

### `roles`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Role ID |
| `name` | string | Internal role name (e.g., `ACCOUNT_OWNER`) |
| `label` | string | Display label |
| `description` | string | Role description |
| `account_id` | integer | Account ID |
| `created_at` | date-time | Creation timestamp |
| `updated_at` | date-time | Last update timestamp |
| `deleted_at` | date-time | Deletion timestamp (null if active) |

### `teams`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Team ID |
| `name` | string | Team name |
| `description` | string | Team description |
| `type` | string | Enum: `SURVEY`, `TICKET` |
| `account_id` | integer | Account ID |
| `business_hour_id` | integer | Business hours configuration ID |
| `round_robin_enabled` | boolean | Whether round-robin assignment is enabled |
| `created_at` | date-time | Creation timestamp |
| `updated_at` | date-time | Last update timestamp |
| `deleted_at` | date-time | Deletion timestamp (null if active) |

### `survey_folders`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Folder ID |
| `name` | string | Folder name (max 100 chars) |
| `description` | string | Folder description (max 200 chars) |
| `auto_created` | boolean | Whether folder was auto-created by the system |
| `visibility` | string | Enum: `ALL`, `PRIVATE` |
| `teams` | integer[] | Team IDs with access |
| `users` | integer[] | User IDs with access |
| `surveys` | object[] | Survey summaries: `{id, name, surveType}` |
| `subfolders` | object[] | Subfolder summaries: `{id, name}` |
| `echoes` | object[] | Echo summaries: `{id, name}` |
| `parent_survey_folder_id` | integer | Parent folder ID (null for root) |
| `created_at` | date-time | Creation timestamp |

### `channels`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Channel ID |
| `name` | string | Channel name |
| `status` | string | Enum: `ACTIVE`, `INACTIVE`, etc. |
| `type` | string | Enum: `EMAIL`, `LINK`, `EMBED`, `QR_CODE`, `SMS`, `WHATSAPP`, `KIOSK`, `SOCIAL_GOOGLE`, `SOCIAL_TWITTER`, `SOCIAL_FACEBOOK`, `OFFLINE`, `EMAIL_EMBED`, `INAPP`, `MOBILE_SDK`, `SYSTEM`, `TEST_EMAIL`, `SLACK`, `TEAMS`, `INTERCOM`, `PORTAL`, `SPOTCHECK`, `SMART_REACH`, `SFTP` |
| `properties` | object | Channel-specific configuration properties |

### `variables`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Variable ID |
| `label` | string | Display label |
| `name` | string | Unique identifier/key |
| `description` | string | Variable description |
| `type` | string | Data type (e.g., `STRING`, `NUMBER`) |

### `tickets`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Ticket ID |
| `requester` | object | Requester contact details |
| `subject` | string | Ticket subject (max 200 chars) |
| `description` | string | Ticket description (plain text) |
| `description_html` | string | Ticket description (HTML) |
| `priority` | object | Priority info `{id, name, label}` |
| `status` | object | Status info `{id, name, label}` |
| `template_id` | integer | Ticket template ID |
| `custom_fields` | object | Custom field key-value pairs |
| `source` | object | Source channel info |
| `agent` | object | Assigned agent info |
| `team` | object | Assigned team info |
| `created_at` | date-time | Creation timestamp |
| `updated_at` | date-time | Last update timestamp |
| `deleted_at` | date-time | Deletion timestamp (null if active) |
| `first_response_due` | date-time | First response SLA deadline |
| `resolution_due` | date-time | Resolution SLA deadline |

### `audit_logs`
| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Audit log entry ID |
| `object` | string | Type of object affected (e.g., `survey`, `user`) |
| `event` | string | Event type enum (e.g., `SURVEY_CREATED`, `LOGIN`) |
| `operation` | string | Operation description (e.g., `Create`) |
| `device` | string | Device type (e.g., `COMPUTER`) |
| `ipAddress` | string | IP address of the actor |
| `time` | date-time | Event timestamp |
| `actor` | object | Actor info: `{id, email, name}` |
| `message` | string | Human-readable description |

### `webhooks`
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Webhook ID |
| `name` | string | Webhook name (max 255 chars) |
| `url` | string | Target URL (max 1000 chars) |
| `eventType` | string | Trigger event type (e.g., `submission_completed`) |
| `description` | string | Description (max 1000 chars) |
| `objectType` | string | Object type (e.g., `survey`) |
| `httpMethod` | string | HTTP method (e.g., `POST`) |
| `headers` | object[] | Custom headers: `[{key, value}]` |
| `properties` | object | Additional properties |
| `payload` | string | Custom payload template |
| `includePartialSubmission` | boolean | Whether partial submissions trigger the webhook |
| `disabled` | boolean | Whether webhook is disabled |

### `targets`
| Field | Type | Description |
|-------|------|-------------|
| `targets` | string[] | List of target identifiers |
| `page` | integer | Current page number |
| `count` | integer | Total count |


## **Get Object Primary Keys**

Primary keys are **static** — no API endpoint needed.

| Object | Primary Key | Type | Notes |
|--------|------------|------|-------|
| `surveys` | `id` | integer | |
| `responses` | `id` | integer | |
| `questions` | `id` | integer | |
| `contacts` | `id` | integer | |
| `contact_lists` | `id` | integer | |
| `contact_properties` | `id` | integer | |
| `users` | `id` | integer | |
| `roles` | `id` | integer | |
| `teams` | `id` | integer | |
| `survey_folders` | `id` | integer | |
| `channels` | `id` | integer | |
| `variables` | `id` | integer | |
| `tickets` | `id` | integer | |
| `audit_logs` | `id` | string (UUID) | e.g. `8190da50-1405-...` |
| `webhooks` | `id` | integer | |
| `targets` | N/A | — | No stable PK; use snapshot ingestion |


## **Object Ingestion Type**

| Object | Ingestion Type | Cursor Field | Notes |
|--------|---------------|--------------|-------|
| `surveys` | `cdc` | `updated_at` | Filter params: `updated_date.gte`, `updated_date.lte` |
| `responses` | `cdc` | `completed_time` | Filter params: `date.gte`, `date.lte` (completedTime); order_by=completedTime |
| `questions` | `snapshot` | — | Partitioned per survey_id; no date filter |
| `contacts` | `cdc` | `createddate` | Filter params: `created_date.gte`, `created_date.lte`; no update cursor |
| `contact_lists` | `snapshot` | — | No date filters |
| `contact_properties` | `snapshot` | — | No date filters |
| `users` | `snapshot` | — | No date filters |
| `roles` | `snapshot` | — | No date filters |
| `teams` | `snapshot` | — | Has `created_at`/`updated_at` in schema but no API filter params |
| `survey_folders` | `snapshot` | — | No date filters |
| `channels` | `snapshot` | — | Partitioned per survey_id; no date filter |
| `variables` | `snapshot` | — | Partitioned per survey_id; no date filter |
| `tickets` | `cdc` | `updated_at` | Filter params: `updated_date.gte`, `updated_date.lte` (format: `YYYY-MM-DDTHH:MM:SS`) |
| `audit_logs` | `append` | `time` | Filter params: `start_date`, `end_date`; append-only by nature |
| `webhooks` | `snapshot` | — | No date filters |
| `targets` | `snapshot` | — | No date filters |


## **Read API for Data Retrieval**

All read operations use **HTTP GET**. Data is returned as JSON with results nested under a `data` key (except `audit_logs` which uses `list`, and `targets` which uses `data.targets`).

### Pagination

All endpoints use **page-based pagination**:
- `page` (integer, default: 1): Current page number
- `limit` (integer): Records per page (endpoint-specific max)
- Response includes `has_next_page: boolean` to determine if more pages follow
- Increment `page` by 1 until `has_next_page` is `false`

| Object | Max `limit` | Default `limit` |
|--------|------------|----------------|
| `surveys` | 100 | 50 |
| `responses` | 200 | 50 |
| `questions` | 100 | 50 |
| `contacts` | 50 | 50 |
| `contact_lists` | N/A | N/A (no pagination params visible) |
| `contact_properties` | N/A | N/A (no pagination params visible) |
| `users` | 50 | 50 |
| `roles` | 100 | 50 |
| `teams` | 100 | 50 |
| `survey_folders` | 100 | 50 |
| `channels` | 100 | 50 |
| `variables` | 100 | 50 |
| `tickets` | 100 | 50 |
| `audit_logs` | 500 | 100 |
| `webhooks` | 100 | 50 |
| `targets` | 200 | 50 |

### Incremental Read Strategy

#### `surveys` (CDC)
```
GET /v3/surveys?updated_date.gte={last_sync}&updated_date.lte={now}&limit=100&page={page}
```
- Cursor field: `updated_at`
- Filter params: `updated_date.gte` / `updated_date.lte` (ISO 8601 date)
- Also supports `created_date.gte` / `created_date.lte` for creation filter
- Lookback: 1 day recommended to catch any delayed writes

#### `responses` (CDC)
```
GET /v3/responses?survey_id={id}&date.gte={last_sync}&date.lte={now}&order_by=completedTime&order=ASC&limit=200&page={page}
```
- Cursor field: `completed_time`
- Filter params: `date.gte` / `date.lte` (filters on `completed_time`)
- Also supports `created_date.gte` / `created_date.lte`
- State param: `state` — possible values: `started`, `completed`, `all` (default: all)
- `survey_id` is **required** — iterate over each configured survey ID
- Lookback: 1 day recommended

#### `contacts` (CDC)
```
GET /v3/contacts?created_date.gte={last_sync}&created_date.lte={now}&limit=50&page={page}
```
- Cursor field: `createddate`
- Note: Only creation date filtering is supported; there is no `updated_date` filter for contacts
- Contact type filter: `contact_type` — `contact` or `employee`

#### `tickets` (CDC)
```
GET /v3/tickets?updated_date.gte={last_sync}&updated_date.lte={now}&limit=100&page={page}
```
- Cursor field: `updated_at`
- Date format: `YYYY-MM-DDTHH:MM:SS`
- Also supports `created_date.gte` / `created_date.lte`

#### `audit_logs` (Append)
```
GET /v3/audit_logs?start_date={last_sync}&end_date={now}&limit=500&page={page}
```
- Cursor field: `time`
- Append-only: events are never updated or deleted once created
- Lookback: none needed (events are immutable)

### Snapshot Objects

Snapshot objects are fetched in full on every sync:
```
GET /v3/{object}?limit={max}&page={page}
```
Continue fetching while `has_next_page == true`.

### Survey-Partitioned Objects

`questions`, `responses`, `channels`, and `variables` require a `survey_id` parameter. The connector must iterate over each survey ID in the user-provided `survey_id` list:
```
GET /v3/questions?survey_id={id}&limit=100&page={page}
GET /v3/channels?survey_id={id}&limit=100&page={page}
GET /v3/variables?survey_id={id}&limit=100&page={page}
```

### Example Requests and Responses

**Get all surveys (incremental)**:
```bash
curl -X GET \
  'https://api.surveysparrow.com/v3/surveys?updated_date.gte=2024-01-01&limit=100&page=1' \
  -H 'Authorization: Bearer your-access-token'
```
Response:
```json
{
  "has_next_page": true,
  "data": [
    {
      "id": 1,
      "name": "Employee Satisfaction Survey",
      "archived": false,
      "survey_type": "Conversational",
      "created_at": "2022-02-28T07:25:44.268Z",
      "updated_at": "2024-01-05T10:00:00.000Z",
      "survey_folder_id": 10000034,
      "survey_folder_name": "General"
    }
  ]
}
```

**Get all responses for a survey (incremental)**:
```bash
curl -X GET \
  'https://api.surveysparrow.com/v3/responses?survey_id=1&date.gte=2024-01-01&order_by=completedTime&order=ASC&limit=200&page=1' \
  -H 'Authorization: Bearer your-access-token'
```
Response:
```json
{
  "total_count": 100,
  "has_next_page": true,
  "data": [
    {
      "id": 1,
      "survey_id": 1,
      "contact_id": 0,
      "completed": "string",
      "channel_id": 3,
      "language": "en",
      "completed_time": "2024-01-05T06:19:04.416Z",
      "answers": [
        {
          "question": "How likely are you to recommend us?",
          "question_tags": ["nps"],
          "question_id": 42,
          "skipped": false
        }
      ],
      "channel": {
        "name": "Email share 1",
        "type": "EMAIL",
        "status": "ACTIVE"
      }
    }
  ]
}
```

**Get audit logs (incremental)**:
```bash
curl -X GET \
  'https://api.surveysparrow.com/v3/audit_logs?start_date=2024-01-01&end_date=2024-01-31&limit=500&page=1' \
  -H 'Authorization: Bearer your-access-token'
```
Response:
```json
{
  "has_next_page": false,
  "count": 3,
  "list": [
    {
      "id": "8190da50-1405-...",
      "object": "survey",
      "survey": {"id": 1, "name": "Untitled"},
      "event": "SURVEY_CREATED",
      "operation": "Create",
      "device": "COMPUTER",
      "ipAddress": "127.0.0.1",
      "time": "2024-01-05T09:40:10.018Z",
      "actor": {"id": 1, "email": "user@example.com", "name": "test"},
      "message": "test has created a new survey Untitled"
    }
  ]
}
```

### Deleted Record Handling

- `responses`: A delete endpoint exists (`DELETE /v3/responses/:id`) but the API does not provide a dedicated feed of deleted records. The `delete_v-3-responses-id` endpoint exists but no soft-delete flag is present in the response schema. **TBD**: Verify if deleted responses appear with a `deleted` flag or are hard-deleted.
- `tickets`: `deleted_at` field is present in the schema. Query with `trash=true` to retrieve only trashed tickets. This allows `cdc_with_deletes` if needed — TBD based on implementation requirements.
- All other objects: No soft-delete indicator found in schemas. Use `snapshot` to overwrite stale data.

### Rate Limits

TBD: SurveySparrow does not publicly document specific rate limits in the V3 API documentation. The API returns HTTP `429 Too Many Requests` when the limit is exceeded. Recommended safe practices:
- Use maximum page sizes (limit parameter) to minimize request count
- Add retry logic with exponential backoff on 429 responses
- Avoid parallel requests across surveys — process surveys sequentially


## **Field Type Mapping**

| API Type | Python/Spark Type | Notes |
|----------|------------------|-------|
| `integer` / `number` | `LongType` / `IntegerType` | Use LongType for IDs |
| `string` | `StringType` | |
| `boolean` | `BooleanType` | |
| `date` / `date-time` (ISO 8601) | `TimestampType` | Parse with `2022-02-28T07:25:44.268Z` format |
| `object` | `StringType` (JSON) or `MapType` | Serialize nested objects as JSON strings |
| `array` | `StringType` (JSON) or `ArrayType` | Serialize arrays as JSON strings |
| `string (UUID)` | `StringType` | Used for `audit_logs.id` |

**Special field behaviors**:
- `answers` in `responses`: Array of objects — each element has `question`, `question_tags[]`, `question_id`, `skipped`; additional answer-specific fields vary by question type. Recommend storing as JSON string.
- `properties` in `questions`: Varies by question type (e.g., contains `text`, `choices`, NPS range settings). Store as JSON string.
- `custom_fields` in `tickets`: Key-value map of user-defined fields. Store as JSON string.
- `completed` in `responses`: String enum — actual values not documented; TBD from live data.
- `survey_type` in `surveys`: Enum — 11 possible values (see schema above).
- `channel.type` in `responses`/`channels`: Enum — 23 possible values (see channels schema).
- Timestamps: Always ISO 8601 with `Z` suffix (UTC). No timezone conversion needed.
- `deleted_at` / `first_response_due` / `resolution_due`: May be `null` when not applicable.


## **Sources and References**

| Source Type | URL | Accessed (UTC) | Confidence | What it confirmed |
|-------------|-----|----------------|------------|-------------------|
| Official API Docs | https://developers.surveysparrow.com/rest-apis/ | 2026-06-03 | High | Full API structure, all endpoint paths |
| Official API Docs — Introduction | https://developers.surveysparrow.com/rest-apis/Introduction | 2026-06-03 | Highest | Auth method, region URLs, response codes |
| Official API Docs — OAuth | https://developers.surveysparrow.com/rest-apis/OAuth | 2026-06-03 | Highest | OAuth 2.0 flow, refresh token exchange |
| Official API Docs — Surveys | https://developers.surveysparrow.com/rest-apis/get-v-3-surveys | 2026-06-03 | Highest | Survey schema, query params, pagination |
| Official API Docs — Responses | https://developers.surveysparrow.com/rest-apis/get-v-3-responses | 2026-06-03 | Highest | Response schema, cursor fields, survey_id requirement |
| Official API Docs — Contacts | https://developers.surveysparrow.com/rest-apis/get-v-3-contacts | 2026-06-03 | Highest | Contacts schema, date filter params |
| Official API Docs — Users | https://developers.surveysparrow.com/rest-apis/get-v-3-users | 2026-06-03 | Highest | Users schema |
| Official API Docs — Questions | https://developers.surveysparrow.com/rest-apis/get-v-3-questions | 2026-06-03 | Highest | Questions schema, survey_id requirement |
| Official API Docs — Audit Logs | https://developers.surveysparrow.com/rest-apis/get-v-3-audit-logs | 2026-06-03 | Highest | Audit logs schema, date filter params, max limit 500 |
| Official API Docs — Tickets | https://developers.surveysparrow.com/rest-apis/get-v-3-tickets | 2026-06-03 | Highest | Tickets schema, cursor fields, trash flag |
| Official API Docs — Channels | https://developers.surveysparrow.com/rest-apis/get-v-3-channels | 2026-06-03 | Highest | Channels schema, survey_id requirement |
| Official API Docs — Teams | https://developers.surveysparrow.com/rest-apis/get-v-3-teams | 2026-06-03 | Highest | Teams schema |
| Official API Docs — Survey Folders | https://developers.surveysparrow.com/rest-apis/get-v-3-survey-folders | 2026-06-03 | Highest | Survey folders schema, subfolders structure |
| Official API Docs — Targets | https://developers.surveysparrow.com/rest-apis/get-v-3-targets | 2026-06-03 | Highest | Targets schema |
| Official API Docs — Variables | https://developers.surveysparrow.com/rest-apis/get-v-3-variables | 2026-06-03 | Highest | Variables schema, survey_id requirement |
| Official API Docs — Webhooks | https://developers.surveysparrow.com/rest-apis/get-v-3-webhooks | 2026-06-03 | Highest | Webhooks schema |
| Official API Docs — Contact Lists | https://developers.surveysparrow.com/rest-apis/get-v-3-contact-lists | 2026-06-03 | Highest | Contact lists schema |
| Official API Docs — Contact Properties | https://developers.surveysparrow.com/rest-apis/get-v-3-contact-properties | 2026-06-03 | Highest | Contact properties schema |
| Airbyte OSS Implementation | https://github.com/airbytehq/airbyte/tree/master/airbyte-integrations/connectors/source-survey-sparrow | 2026-06-03 | High | Streams: contacts, contact_lists, questions, responses, roles, surveys, survey_folders, users; BearerAuth; page-increment pagination; survey_id partition routing |

**Known Quirks / Conflicts**:
- Airbyte implements only 8 streams (contacts, contact_lists, questions, responses, roles, surveys, survey_folders, users). This connector adds 8 more (audit_logs, channels, contact_properties, teams, tickets, variables, webhooks, targets) based on official API docs.
- Airbyte's region config only exposes US and EU. This connector exposes all 7 regions per the official docs.
- `contact_lists` response in the official docs shows `data: string[]` (unclear schema), while Airbyte's schema defines specific properties (`id`, `name`, `description`, `created_at`). Airbyte schema used as authoritative since it aligns with common REST patterns. TBD: Verify via live testing.
- Rate limits are not publicly documented. TBD: Test empirically or contact SurveySparrow support.
- `responses` cursor uses `date.gte`/`date.lte` which maps to `completed_time`. For responses that are never completed (started state), the `completed_time` may be null — use `state=all` and `created_date.gte` as an alternative cursor if needed.

## **Research Log**

| Source Type | URL | Accessed (UTC) | Confidence | What it confirmed |
|-------------|-----|----------------|------------|-------------------|
| Official Docs | https://developers.surveysparrow.com/rest-apis/Introduction | 2026-06-03 | Highest | Auth (Bearer Token + OAuth), region base URLs, HTTP status codes |
| Official Docs | https://developers.surveysparrow.com/rest-apis/OAuth | 2026-06-03 | Highest | OAuth 2.0 auth flow, refresh token exchange payload |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-surveys | 2026-06-03 | Highest | Surveys schema, pagination, incremental filter params |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-responses | 2026-06-03 | Highest | Responses schema, cursor (date.gte/lte), survey_id requirement |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-contacts | 2026-06-03 | Highest | Contacts schema, created_date filters, limit=50 max |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-users | 2026-06-03 | Highest | Users schema, limit=50 max |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-questions | 2026-06-03 | Highest | Questions schema, survey_id required, limit=100 max |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-audit-logs | 2026-06-03 | Highest | Audit logs schema, start_date/end_date filters, max limit=500, response key=list |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-tickets | 2026-06-03 | Highest | Tickets schema, created/updated date filters, trash param |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-channels | 2026-06-03 | Highest | Channels schema, survey_id required, channel types enum |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-teams | 2026-06-03 | Highest | Teams schema, type enum (SURVEY/TICKET) |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-survey-folders | 2026-06-03 | Highest | Survey folders schema, nested structure |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-variables | 2026-06-03 | Highest | Variables schema, survey_id required |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-webhooks | 2026-06-03 | Highest | Webhooks schema |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-contact-lists | 2026-06-03 | Highest | Contact lists schema |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-contact-properties | 2026-06-03 | Highest | Contact properties schema |
| Official Docs | https://developers.surveysparrow.com/rest-apis/get-v-3-targets | 2026-06-03 | Highest | Targets schema |
| Airbyte OSS | https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-survey-sparrow/manifest.yaml | 2026-06-03 | High | Confirmed 8 streams, BearerAuth, page-increment pagination, survey_id partition routing, detailed field schemas |
