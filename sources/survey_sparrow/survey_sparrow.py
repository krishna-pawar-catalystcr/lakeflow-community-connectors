"""SurveySparrow community connector — implements LakeflowConnect for the SurveySparrow V3 REST API."""

import time
import urllib.error
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta, timezone
from typing import Iterator

from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from databricks.labs.community_connector.interface.lakeflow_connect import LakeflowConnect

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REGION_URLS: dict[str, str] = {
    "us":    "https://api.surveysparrow.com/v3",
    "eu":    "https://eu-api.surveysparrow.com/v3",
    "ap":    "https://ap-api.surveysparrow.com/v3",
    "me":    "https://me-api.surveysparrow.com/v3",
    "uk":    "https://eu-ln-api.surveysparrow.com/v3",
    "ap-sy": "https://ap-sy-api.surveysparrow.com/v3",
    "ca":    "https://ca-api.surveysparrow.com/v3",
}

_SUPPORTED_TABLES: list[str] = [
    "surveys",
    "responses",
    "questions",
    "contacts",
    "contact_lists",
    "contact_properties",
    "users",
    "roles",
    "teams",
    "survey_folders",
    "channels",
    "variables",
    "tickets",
    "audit_logs",
    "webhooks",
    "targets",
]

# Tables that require a survey_id to be passed in table_options
_SURVEY_PARTITIONED: set[str] = {"responses", "questions", "channels", "variables"}

# ---------------------------------------------------------------------------
# Static schemas
# ---------------------------------------------------------------------------

_ANSWER_SCHEMA = StructType([
    StructField("question",      StringType(),          True),
    StructField("question_tags", ArrayType(StringType()), True),
    StructField("question_id",   LongType(),            True),
    StructField("skipped",       BooleanType(),         True),
])

_CHANNEL_EMBED_SCHEMA = StructType([
    StructField("name",   StringType(), True),
    StructField("type",   StringType(), True),
    StructField("status", StringType(), True),
])

TABLE_SCHEMAS: dict[str, StructType] = {
    "surveys": StructType([
        StructField("id",                 LongType(),    False),
        StructField("name",               StringType(),  True),
        StructField("archived",           BooleanType(), True),
        StructField("survey_type",        StringType(),  True),
        StructField("created_at",         StringType(),  True),
        StructField("updated_at",         StringType(),  True),
        StructField("survey_folder_id",   LongType(),    True),
        StructField("survey_folder_name", StringType(),  True),
    ]),
    "responses": StructType([
        StructField("id",             LongType(),              False),
        StructField("survey_id",      LongType(),              True),
        StructField("contact_id",     LongType(),              True),
        StructField("completed",      StringType(),            True),
        StructField("channel_id",     LongType(),              True),
        StructField("language",       StringType(),            True),
        StructField("completed_time", StringType(),            True),
        StructField("answers",        StringType(),            True),  # JSON array
        StructField("channel",        StringType(),            True),  # JSON object
        StructField("contact",        StringType(),            True),  # JSON object/string
        StructField("expressions",    StringType(),            True),  # JSON array
    ]),
    "questions": StructType([
        StructField("id",                  LongType(),    False),
        StructField("type",                StringType(),  True),
        StructField("position",            StringType(),  True),
        StructField("hasDisplayLogic",     BooleanType(), True),
        StructField("properties",          StringType(),  True),  # JSON object
        StructField("survey_id",           LongType(),    True),
        StructField("section_id",          LongType(),    True),
        StructField("account_id",          LongType(),    True),
        StructField("parent_question_id",  LongType(),    True),
        StructField("choices",             StringType(),  True),  # JSON array
        StructField("annotations",         StringType(),  True),  # JSON array
        StructField("created_at",          StringType(),  True),
        StructField("is_required",         BooleanType(), True),
        StructField("multiple_answers",    BooleanType(), True),
    ]),
    "contacts": StructType([
        StructField("id",           LongType(),    False),
        StructField("active",       BooleanType(), True),
        StructField("email",        StringType(),  True),
        StructField("first_name",   StringType(),  True),
        StructField("last_name",    StringType(),  True),
        StructField("name",         StringType(),  True),
        StructField("job_title",    StringType(),  True),
        StructField("mobile",       StringType(),  True),
        StructField("unsubscribed", BooleanType(), True),
        StructField("createddate",  StringType(),  True),
    ]),
    "contact_lists": StructType([
        StructField("id",          LongType(),   False),
        StructField("name",        StringType(), True),
        StructField("description", StringType(), True),
        StructField("created_at",  StringType(), True),
    ]),
    "contact_properties": StructType([
        StructField("id",                       LongType(),   False),
        StructField("name",                     StringType(), True),
        StructField("label",                    StringType(), True),
        StructField("type",                     StringType(), True),
        StructField("description",              StringType(), True),
        StructField("contact_property_group_id", LongType(),  True),
        StructField("group",                    StringType(), True),
    ]),
    "users": StructType([
        StructField("id",            LongType(),    False),
        StructField("name",          StringType(),  True),
        StructField("email",         StringType(),  True),
        StructField("phone",         StringType(),  True),
        StructField("admin",         BooleanType(), True),
        StructField("owner",         BooleanType(), True),
        StructField("agency_owner",  BooleanType(), True),
        StructField("verified",      BooleanType(), True),
        StructField("role_id",       LongType(),    True),
        StructField("created_at",    StringType(),  True),
    ]),
    "roles": StructType([
        StructField("id",          LongType(),   False),
        StructField("name",        StringType(), True),
        StructField("label",       StringType(), True),
        StructField("description", StringType(), True),
        StructField("account_id",  LongType(),   True),
        StructField("created_at",  StringType(), True),
        StructField("updated_at",  StringType(), True),
        StructField("deleted_at",  StringType(), True),
    ]),
    "teams": StructType([
        StructField("id",                   LongType(),    False),
        StructField("name",                 StringType(),  True),
        StructField("description",          StringType(),  True),
        StructField("type",                 StringType(),  True),
        StructField("account_id",           LongType(),    True),
        StructField("business_hour_id",     LongType(),    True),
        StructField("round_robin_enabled",  BooleanType(), True),
        StructField("created_at",           StringType(),  True),
        StructField("updated_at",           StringType(),  True),
        StructField("deleted_at",           StringType(),  True),
    ]),
    "survey_folders": StructType([
        StructField("id",                      LongType(),   False),
        StructField("name",                    StringType(), True),
        StructField("description",             StringType(), True),
        StructField("auto_created",            BooleanType(), True),
        StructField("visibility",              StringType(), True),
        StructField("teams",                   StringType(), True),  # JSON array of ints
        StructField("users",                   StringType(), True),  # JSON array of ints
        StructField("surveys",                 StringType(), True),  # JSON array of objects
        StructField("parent_survey_folder_id", LongType(),   True),
        StructField("subfolders",              StringType(), True),  # JSON array
        StructField("echoes",                  StringType(), True),  # JSON array
        StructField("created_at",              StringType(), True),
    ]),
    "channels": StructType([
        StructField("id",         LongType(),   False),
        StructField("survey_id",  LongType(),   True),
        StructField("name",       StringType(), True),
        StructField("status",     StringType(), True),
        StructField("type",       StringType(), True),
        StructField("properties", StringType(), True),  # JSON object
    ]),
    "variables": StructType([
        StructField("id",          LongType(),   False),
        StructField("survey_id",   LongType(),   True),
        StructField("label",       StringType(), True),
        StructField("name",        StringType(), True),
        StructField("description", StringType(), True),
        StructField("type",        StringType(), True),
    ]),
    "tickets": StructType([
        StructField("id",                   LongType(),   False),
        StructField("requester",            StringType(), True),  # JSON object
        StructField("subject",              StringType(), True),
        StructField("description",          StringType(), True),
        StructField("description_html",     StringType(), True),
        StructField("priority",             StringType(), True),  # JSON object
        StructField("status",               StringType(), True),  # JSON object
        StructField("template_id",          LongType(),   True),
        StructField("custom_fields",        StringType(), True),  # JSON object
        StructField("source",               StringType(), True),  # JSON object
        StructField("agent",                StringType(), True),  # JSON object
        StructField("team",                 StringType(), True),  # JSON object
        StructField("created_at",           StringType(), True),
        StructField("updated_at",           StringType(), True),
        StructField("deleted_at",           StringType(), True),
        StructField("first_response_due",   StringType(), True),
        StructField("resolution_due",       StringType(), True),
    ]),
    "audit_logs": StructType([
        StructField("id",         StringType(), False),  # UUID string
        StructField("object",     StringType(), True),
        StructField("event",      StringType(), True),
        StructField("operation",  StringType(), True),
        StructField("device",     StringType(), True),
        StructField("ipAddress",  StringType(), True),
        StructField("time",       StringType(), True),
        StructField("actor",      StringType(), True),  # JSON object
        StructField("message",    StringType(), True),
    ]),
    "webhooks": StructType([
        StructField("id",                      LongType(),    False),
        StructField("name",                    StringType(),  True),
        StructField("url",                     StringType(),  True),
        StructField("eventType",               StringType(),  True),
        StructField("description",             StringType(),  True),
        StructField("objectType",              StringType(),  True),
        StructField("httpMethod",              StringType(),  True),
        StructField("headers",                 StringType(),  True),  # JSON array
        StructField("properties",              StringType(),  True),  # JSON object
        StructField("payload",                 StringType(),  True),
        StructField("includePartialSubmission", BooleanType(), True),
        StructField("disabled",                BooleanType(), True),
    ]),
    "targets": StructType([
        StructField("targets", StringType(), True),  # JSON array of strings
        StructField("page",    LongType(),   True),
        StructField("count",   LongType(),   True),
    ]),
}

# ---------------------------------------------------------------------------
# Per-table ingestion metadata
# ---------------------------------------------------------------------------

_TABLE_METADATA: dict[str, dict] = {
    "surveys":            {"ingestion_type": "cdc",      "primary_keys": ["id"], "cursor_field": "updated_at"},
    "responses":          {"ingestion_type": "cdc",      "primary_keys": ["id"], "cursor_field": "completed_time"},
    "questions":          {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "contacts":           {"ingestion_type": "cdc",      "primary_keys": ["id"], "cursor_field": "createddate"},
    "contact_lists":      {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "contact_properties": {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "users":              {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "roles":              {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "teams":              {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "survey_folders":     {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "channels":           {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "variables":          {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "tickets":            {"ingestion_type": "cdc",      "primary_keys": ["id"], "cursor_field": "updated_at"},
    "audit_logs":         {"ingestion_type": "append",   "primary_keys": ["id"], "cursor_field": "time"},
    "webhooks":           {"ingestion_type": "snapshot", "primary_keys": ["id"], "cursor_field": None},
    "targets":            {"ingestion_type": "snapshot", "primary_keys": [],     "cursor_field": None},
}

# Retry config
_INITIAL_BACKOFF = 1.0
_MAX_RETRIES = 4
_RETRIABLE_CODES = {429, 500, 502, 503, 504}
_LOOKBACK_SECONDS = 60
_DEFAULT_WINDOW_SECONDS = 3600  # Strategy A default: 1-hour sliding window


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class SurveySparrowLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for the SurveySparrow V3 REST API."""

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)
        self._token = options["access_token"]
        region = options.get("region", "us").lower()
        self._base_url = _REGION_URLS.get(region, _REGION_URLS["us"])
        # Cap cursors at init time to prevent chasing actively written data.
        self._init_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        self._lookback_applied: set[str] = set()

    # -----------------------------------------------------------------------
    # Interface implementation
    # -----------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return _SUPPORTED_TABLES.copy()

    def get_table_schema(
        self, table_name: str, table_options: dict[str, str]
    ) -> StructType:
        self._validate_table(table_name)
        return TABLE_SCHEMAS[table_name]

    def read_table_metadata(
        self, table_name: str, table_options: dict[str, str]
    ) -> dict:
        self._validate_table(table_name)
        meta = _TABLE_METADATA[table_name]
        result: dict = {
            "primary_keys": meta["primary_keys"],
            "ingestion_type": meta["ingestion_type"],
        }
        if meta["ingestion_type"] in ("cdc", "append") and meta["cursor_field"]:
            result["cursor_field"] = meta["cursor_field"]
        return result

    def read_table(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        self._validate_table(table_name)
        ingestion_type = _TABLE_METADATA[table_name]["ingestion_type"]

        if ingestion_type == "snapshot":
            return self._read_snapshot(table_name, table_options)
        elif ingestion_type == "append":
            return self._read_append(table_name, start_offset, table_options)
        else:  # cdc
            return self._read_cdc(table_name, start_offset, table_options)

    # -----------------------------------------------------------------------
    # Snapshot read
    # -----------------------------------------------------------------------

    def _read_snapshot(
        self, table_name: str, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        """Full-refresh: paginate all pages and return offset={}."""
        if table_name in _SURVEY_PARTITIONED:
            records = self._read_survey_partitioned_snapshot(table_name, table_options)
        else:
            records = self._paginate_all(table_name, {})
        return iter(records), {}

    def _read_survey_partitioned_snapshot(
        self, table_name: str, table_options: dict[str, str]
    ) -> list[dict]:
        """Read a survey-partitioned table.  If survey_id provided use it;
        otherwise iterate over all surveys."""
        survey_ids = self._resolve_survey_ids(table_options)
        records: list[dict] = []
        for sid in survey_ids:
            batch = self._paginate_all(table_name, {"survey_id": str(sid)})
            for rec in batch:
                rec["survey_id"] = sid
            records.extend(batch)
        return records

    # -----------------------------------------------------------------------
    # CDC read
    # -----------------------------------------------------------------------

    def _read_cdc(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        """Incremental CDC read bounded by max_records_per_batch."""
        cursor_field = _TABLE_METADATA[table_name]["cursor_field"]
        since = start_offset.get("cursor") if start_offset else None

        # Short-circuit: already caught up to init time.
        if since and since >= self._init_ts:
            return iter([]), start_offset

        # Apply lookback once per trigger per table.
        effective_since = since
        if since and table_name not in self._lookback_applied:
            self._lookback_applied.add(table_name)
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            effective_since = (dt - timedelta(seconds=_LOOKBACK_SECONDS)).isoformat()

        # Strategy A: bounded sliding time-window (only when a starting cursor exists).
        until: str | None = None
        if effective_since:
            window_secs = int(table_options.get("window_seconds", str(_DEFAULT_WINDOW_SECONDS)))
            dt_since = datetime.fromisoformat(effective_since.replace("Z", "+00:00"))
            dt_until = dt_since + timedelta(seconds=window_secs)
            dt_init = datetime.fromisoformat(self._init_ts.replace("Z", "+00:00"))
            if dt_until > dt_init:
                dt_until = dt_init
            until = dt_until.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        max_records = int(table_options.get("max_records_per_batch", "200"))

        if table_name in _SURVEY_PARTITIONED:
            records = self._read_cdc_survey_partitioned(
                table_name, effective_since, until, table_options, max_records
            )
        else:
            params = self._build_cdc_params(table_name, effective_since, until)
            records = []
            page = 1
            while len(records) < max_records:
                params["page"] = str(page)
                params["limit"] = str(
                    min(self._page_limit(table_name), max_records - len(records))
                )
                batch, has_next = self._fetch_page(table_name, params)
                if not batch:
                    break
                records.extend(batch)
                if not has_next:
                    break
                page += 1

        if not records:
            # Advance the cursor to the window end so the next call slides forward.
            if until:
                return iter([]), {"cursor": until}
            return iter([]), start_offset or {}

        last_cursor = records[-1].get(cursor_field, "")
        end_offset = {"cursor": last_cursor}
        if start_offset and start_offset == end_offset:
            return iter([]), start_offset
        return iter(records), end_offset

    def _read_cdc_survey_partitioned(
        self,
        table_name: str,
        since: str | None,
        until: str | None,
        table_options: dict[str, str],
        max_records: int,
    ) -> list[dict]:
        survey_ids = self._resolve_survey_ids(table_options)
        cursor_field = _TABLE_METADATA[table_name]["cursor_field"]
        records: list[dict] = []
        for sid in survey_ids:
            if len(records) >= max_records:
                break
            params = self._build_cdc_params(table_name, since, until)
            params["survey_id"] = str(sid)
            page = 1
            while len(records) < max_records:
                params["page"] = str(page)
                params["limit"] = str(
                    min(self._page_limit(table_name), max_records - len(records))
                )
                batch, has_next = self._fetch_page(table_name, params)
                if not batch:
                    break
                for rec in batch:
                    rec["survey_id"] = sid
                records.extend(batch)
                if not has_next:
                    break
                page += 1
        return records

    # -----------------------------------------------------------------------
    # Append read (audit_logs)
    # -----------------------------------------------------------------------

    def _read_append(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        """Append-only read for audit_logs.  Uses server-side limit to avoid
        cutting mid-page (no client-side truncation)."""
        cursor_field = _TABLE_METADATA[table_name]["cursor_field"]
        since = start_offset.get("cursor") if start_offset else None

        if since and since >= self._init_ts:
            return iter([]), start_offset

        limit = int(table_options.get("limit", "100"))
        max_records = int(table_options.get("max_records_per_batch", "200"))

        params: dict[str, str] = {"limit": str(min(limit, 500))}
        if since:
            params["start_date"] = since

        records: list[dict] = []
        page = 1
        while len(records) < max_records:
            params["page"] = str(page)
            batch, has_next = self._fetch_page(table_name, params)
            if not batch:
                break
            # For audit_logs, API returns records under "list" key; _fetch_page handles this
            records.extend(batch)
            # For append: process full pages, stop after max_records threshold is reached
            if len(records) >= max_records:
                break
            if not has_next:
                break
            page += 1

        if not records:
            return iter([]), start_offset or {}

        last_cursor = records[-1].get(cursor_field, "")
        end_offset = {"cursor": last_cursor}
        if start_offset and start_offset == end_offset:
            return iter([]), start_offset
        return iter(records), end_offset

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    def _get(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict:
        """Make a GET request with retry on transient errors."""
        url = self._base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        backoff = _INITIAL_BACKOFF
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {self._token}"}
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code not in _RETRIABLE_CODES:
                    raise
                last_exc = exc
            except OSError as exc:
                last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

        raise RuntimeError(f"Request failed after {_MAX_RETRIES} attempts: {last_exc}")

    def _fetch_page(
        self, table_name: str, params: dict[str, str]
    ) -> tuple[list[dict], bool]:
        """Fetch one page for table_name and return (records, has_next_page)."""
        path = _table_path(table_name)
        body = self._get(path, params)

        # audit_logs uses "list" key; all others use "data"
        if table_name == "audit_logs":
            records = body.get("list", [])
        elif table_name == "targets":
            # targets wraps results under data.targets
            inner = body.get("data", {})
            if isinstance(inner, dict):
                raw_targets = inner.get("targets", [])
                has_next = inner.get("has_next_page", False)
                return [{"targets": json.dumps(raw_targets),
                         "page":    inner.get("page"),
                         "count":   inner.get("count")}], has_next
            records = []
        else:
            records = body.get("data", [])

        # Serialize complex fields
        records = [_serialize_complex(r) for r in records]
        has_next = body.get("has_next_page", False)
        return records, has_next

    def _paginate_all(
        self, table_name: str, extra_params: dict[str, str]
    ) -> list[dict]:
        """Paginate a snapshot table until has_next_page is False."""
        records: list[dict] = []
        page = 1
        limit = self._page_limit(table_name)
        while True:
            params = {"page": str(page), "limit": str(limit), **extra_params}
            batch, has_next = self._fetch_page(table_name, params)
            records.extend(batch)
            if not has_next:
                break
            page += 1
        return records

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _validate_table(self, table_name: str) -> None:
        if table_name not in _SUPPORTED_TABLES:
            raise ValueError(
                f"Table '{table_name}' is not supported. "
                f"Supported tables: {_SUPPORTED_TABLES}"
            )

    def _resolve_survey_ids(self, table_options: dict[str, str]) -> list[int]:
        """Return survey IDs from table_options, or fetch all surveys if not provided."""
        raw = table_options.get("survey_id", "")
        if raw:
            # Accept comma-separated or single id
            return [int(s.strip()) for s in raw.split(",") if s.strip()]
        # Fallback: list all surveys
        all_surveys = self._paginate_all("surveys", {})
        return [s["id"] for s in all_surveys if s.get("id")]

    @staticmethod
    def _build_cdc_params(
        table_name: str, since: str | None, until: str | None = None
    ) -> dict[str, str]:
        """Build query params for an incremental read on table_name.

        Supports Strategy A: when ``until`` is provided it adds the matching
        upper-bound filter so the server scans only a bounded time window.
        """
        params: dict[str, str] = {}
        if since:
            if table_name == "surveys":
                params["updated_date.gte"] = since
                if until:
                    params["updated_date.lte"] = until
            elif table_name == "responses":
                params["date.gte"] = since
                if until:
                    params["date.lte"] = until
                params["order_by"] = "completedTime"
                params["order"] = "ASC"
            elif table_name == "contacts":
                params["created_date.gte"] = since
                if until:
                    params["created_date.lte"] = until
            elif table_name == "tickets":
                params["updated_date.gte"] = _fmt_ticket_ts(since)
                if until:
                    params["updated_date.lte"] = _fmt_ticket_ts(until)
        return params

    @staticmethod
    def _page_limit(table_name: str) -> int:
        _limits: dict[str, int] = {
            "surveys": 100,
            "responses": 200,
            "questions": 100,
            "contacts": 50,
            "users": 50,
            "roles": 100,
            "teams": 100,
            "survey_folders": 100,
            "channels": 100,
            "variables": 100,
            "tickets": 100,
            "audit_logs": 500,
            "webhooks": 100,
            "targets": 200,
            "contact_lists": 50,
            "contact_properties": 50,
        }
        return _limits.get(table_name, 50)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _fmt_ticket_ts(ts: str) -> str:
    """Normalise a timestamp to the format expected by the tickets API: YYYY-MM-DDTHH:MM:SS."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _table_path(table_name: str) -> str:
    """Map table name to API path segment."""
    _paths: dict[str, str] = {
        "surveys":            "/surveys",
        "responses":          "/responses",
        "questions":          "/questions",
        "contacts":           "/contacts",
        "contact_lists":      "/contact_lists",
        "contact_properties": "/contact_properties",
        "users":              "/users",
        "roles":              "/roles",
        "teams":              "/teams",
        "survey_folders":     "/survey_folders",
        "channels":           "/channels",
        "variables":          "/variables",
        "tickets":            "/tickets",
        "audit_logs":         "/audit_logs",
        "webhooks":           "/webhooks",
        "targets":            "/targets",
    }
    return _paths[table_name]


_COMPLEX_FIELDS: set[str] = {
    "answers", "channel", "contact", "expressions",
    "properties", "choices", "annotations",
    "requester", "priority", "status", "custom_fields", "source", "agent", "team",
    "actor",
    "headers",
    "teams", "users", "surveys", "subfolders", "echoes",
}


def _serialize_complex(record: dict) -> dict:
    """JSON-serialize any dict/list fields so Spark sees them as StringType."""
    result = {}
    for k, v in record.items():
        if k in _COMPLEX_FIELDS and isinstance(v, (dict, list)):
            result[k] = json.dumps(v)
        else:
            result[k] = v
    return result
