"""Medidata eTMF source connector.

Connects to Medidata's eTMF system via MAuth-signed HTTP requests.
Data is extracted through a two-step report-based process:

1. ``GET /fetch_reports`` — list available reports (paginated, offset-based)
2. ``GET /regulated_files/{uuid}/content`` — download report as Excel binary

Three report types are supported as snapshot tables:
- **etmf_full_details** — comprehensive document-level details
- **etmf_filed_docs** — summary of filed/finalized documents
- **etmf_rejections** — document rejection records
"""

import re
import time
from io import BytesIO
from typing import Iterator

import pandas as pd
import requests
from mauth_client.requests_mauth import MAuth
from pyspark.sql.types import StringType, StructField, StructType

from databricks.labs.community_connector.interface import LakeflowConnect

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RETRIABLE_STATUS_CODES = {408, 429, 500, 502, 503}
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0
DEFAULT_BASE_URL = "https://api.mdsol.com"
DEFAULT_PAGE_SIZE = 1000
REQUEST_TIMEOUT = 120

REPORT_NAME_PATTERN = re.compile(
    r"(All Studies_KPI Rejections|.*_KPI Full Details|.*_KPI Total Filed Docs)",
    re.IGNORECASE,
)

REPORT_TYPE_TO_TABLE = {
    "eTMF Document Full Details": "etmf_full_details",
    "eTMF Filed Documents": "etmf_filed_docs",
    "Rejections": "etmf_rejections",
}

TABLE_TO_REPORT_TYPE = {v: k for k, v in REPORT_TYPE_TO_TABLE.items()}

SUPPORTED_TABLES = ["etmf_full_details", "etmf_filed_docs", "etmf_rejections"]

# ---------------------------------------------------------------------------
# Static schemas — all string since data comes from Excel with dtype=str
# ---------------------------------------------------------------------------

FULL_DETAILS_COLUMN_MAP = {
    "Document Identifier": "document_id",
    "Level": "level",
    "Study": "study",
    "Environment": "environment",
    "Site": "site",
    "Folder Path": "folder_path",
    "Zone": "zone",
    "Artifact #": "artifact",
    "Name": "name",
    "Version": "version",
    "State": "state",
    "WF Type": "wf_type",
    "Initiator": "initiator",
    "Created On (User)": "created_by",
    "Edit Completed / Rejected By": "edit_completed_rejected_by",
    "Created On (Date/Time)": "created_at",
    "Document Property: Document Date": "document_date",
}

ETMF_FULL_DETAILS_SCHEMA = StructType(
    [
        StructField("document_id", StringType(), nullable=True),
        StructField("fsi_uuid", StringType(), nullable=True),
        StructField("level", StringType(), nullable=True),
        StructField("study", StringType(), nullable=True),
        StructField("environment", StringType(), nullable=True),
        StructField("site", StringType(), nullable=True),
        StructField("folder_path", StringType(), nullable=True),
        StructField("zone", StringType(), nullable=True),
        StructField("artifact", StringType(), nullable=True),
        StructField("name", StringType(), nullable=True),
        StructField("version", StringType(), nullable=True),
        StructField("state", StringType(), nullable=True),
        StructField("wf_type", StringType(), nullable=True),
        StructField("initiator", StringType(), nullable=True),
        StructField("created_by", StringType(), nullable=True),
        StructField("edit_completed_rejected_by", StringType(), nullable=True),
        StructField("created_at", StringType(), nullable=True),
        StructField("document_date", StringType(), nullable=True),
    ]
)

ETMF_FILED_DOCS_SCHEMA = StructType(
    [
        StructField("document_name", StringType(), nullable=True),
        StructField("folder_path", StringType(), nullable=True),
        StructField("study", StringType(), nullable=True),
        StructField("country", StringType(), nullable=True),
        StructField("site", StringType(), nullable=True),
        StructField("zone", StringType(), nullable=True),
        StructField("section", StringType(), nullable=True),
        StructField("artifact_#", StringType(), nullable=True),
        StructField("format", StringType(), nullable=True),
        StructField("created_on", StringType(), nullable=True),
        StructField("created_by", StringType(), nullable=True),
        StructField("document_title", StringType(), nullable=True),
        StructField("version", StringType(), nullable=True),
        StructField("updated_on", StringType(), nullable=True),
        StructField("uuid", StringType(), nullable=True),
    ]
)

ETMF_REJECTIONS_SCHEMA = StructType(
    [
        StructField("document_name", StringType(), nullable=True),
        StructField("folder_path", StringType(), nullable=True),
        StructField("rejected_date", StringType(), nullable=True),
        StructField("rejected_by", StringType(), nullable=True),
        StructField("rejection_reason", StringType(), nullable=True),
        StructField("comment", StringType(), nullable=True),
        StructField("open", StringType(), nullable=True),
        StructField("finalized_version", StringType(), nullable=True),
        StructField("finalized_document_state", StringType(), nullable=True),
        StructField("owner", StringType(), nullable=True),
        StructField("version", StringType(), nullable=True),
        StructField("study", StringType(), nullable=True),
        StructField("site", StringType(), nullable=True),
        StructField("uuid", StringType(), nullable=True),
    ]
)

TABLE_SCHEMAS = {
    "etmf_full_details": ETMF_FULL_DETAILS_SCHEMA,
    "etmf_filed_docs": ETMF_FILED_DOCS_SCHEMA,
    "etmf_rejections": ETMF_REJECTIONS_SCHEMA,
}

TABLE_METADATA = {
    "etmf_full_details": {
        "primary_keys": ["document_id", "fsi_uuid"],
        "cursor_field": "",
        "ingestion_type": "snapshot",
    },
    "etmf_filed_docs": {
        "primary_keys": ["document_name", "folder_path", "study", "uuid"],
        "cursor_field": "",
        "ingestion_type": "snapshot",
    },
    "etmf_rejections": {
        "primary_keys": ["document_name", "folder_path", "rejected_date", "uuid"],
        "cursor_field": "",
        "ingestion_type": "snapshot",
    },
}


class MedidataEtmfLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for Medidata eTMF.

    Authentication uses Medidata's MAuth protocol (request signing with
    RSA private key). Data is extracted from pre-generated Excel reports
    via a two-step API call pattern.
    """

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)

        app_uuid = options["app_uuid"]
        private_key = options["private_key"]
        self._client_division_scheme_uuid = options["client_division_scheme_uuid"]
        self._base_url = options.get("base_url", DEFAULT_BASE_URL).rstrip("/")

        self._mauth = MAuth(app_uuid, private_key)
        self._headers = {
            "Accept": "application/json",
            "Mcc-Version": "v2019-04-12",
        }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _request_with_retry(
        self, url: str, params: dict | None = None
    ) -> requests.Response:
        """Issue a GET request with MAuth signing and exponential backoff."""
        backoff = INITIAL_BACKOFF
        last_resp = None
        for attempt in range(MAX_RETRIES):
            resp = requests.get(
                url,
                auth=self._mauth,
                headers=self._headers,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code not in RETRIABLE_STATUS_CODES:
                return resp
            last_resp = resp
            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2

        return last_resp  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Report discovery helpers
    # ------------------------------------------------------------------

    def _fetch_all_reports(
        self,
        created_at_from: int | None = None,
        created_at_to: int | None = None,
    ) -> list[dict]:
        """Fetch all report listings from ``GET /fetch_reports``.

        Args:
            created_at_from: Start of time window (epoch ms). If None, defaults
                to start of first day of current month (00:00:00 UTC).
            created_at_to: End of time window (epoch ms). If None, defaults to
                end of first day of current month (23:59:59 UTC).
        """
        from datetime import datetime, timezone

        if created_at_from is None:
            now = datetime.now(timezone.utc)
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            created_at_from = int(start.timestamp() * 1000)
        if created_at_to is None:
            now = datetime.now(timezone.utc)
            end = datetime(now.year, now.month, 1, 23, 59, 59, tzinfo=timezone.utc)
            created_at_to = int(end.timestamp() * 1000)

        url = f"{self._base_url}/fetch_reports"
        params: dict = {
            "client_division_scheme_uuid": self._client_division_scheme_uuid,
            "show_obsoleted": False,
            "created_at_from": created_at_from,
            "created_at_to": created_at_to,
            "pageSize": DEFAULT_PAGE_SIZE,
            "pageStart": 0,
        }

        all_elements: list[dict] = []
        has_next_page = True

        while has_next_page:
            resp = self._request_with_retry(url, params=params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to fetch reports: HTTP {resp.status_code} — {resp.text}"
                )
            data = resp.json()
            children = data.get("children", {})
            all_elements.extend(children.get("elements", []))
            has_next_page = children.get("hasNextPage", False)
            params["pageStart"] = params["pageStart"] + params["pageSize"]

        return all_elements

    def _get_latest_report_uuids(
        self, reports: list[dict], report_type: str
    ) -> list[str]:
        """Filter reports by type, group by study, take latest by updatedAt."""
        if not reports:
            return []

        df = pd.DataFrame(reports)
        # Use non-capturing pattern for .str.contains (avoids group warning)
        filter_pattern = REPORT_NAME_PATTERN.pattern.replace("(", "(?:")
        matched = df[
            df["name"].str.contains(
                filter_pattern, case=False, na=False, regex=True
            )
        ].copy()

        if matched.empty:
            return []

        matched["matched_study"] = matched["name"].str.extract(
            REPORT_NAME_PATTERN, expand=False
        )

        typed = matched[matched["systemFolderTypeLocalized"] == report_type].copy()
        if typed.empty:
            return []

        typed["updatedAt"] = pd.to_numeric(typed["updatedAt"], errors="coerce")
        typed = typed.sort_values(
            ["matched_study", "updatedAt"], ascending=[True, False]
        )
        latest = typed.groupby("matched_study", as_index=False).first()
        return latest["uuid"].tolist()

    def _download_report(self, fsi_uuid: str) -> pd.DataFrame:
        """Download a single report Excel file and parse as DataFrame."""
        url = f"{self._base_url}/regulated_files/{fsi_uuid}/content"
        params = {
            "client_division_scheme_uuid": self._client_division_scheme_uuid,
        }
        resp = self._request_with_retry(url, params=params)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to download report {fsi_uuid}: "
                f"HTTP {resp.status_code} — {resp.text}"
            )
        return pd.read_excel(BytesIO(resp.content), dtype=str)

    # ------------------------------------------------------------------
    # LakeflowConnect interface
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        """Return the static list of supported tables."""
        return list(SUPPORTED_TABLES)

    def get_table_schema(
        self, table_name: str, table_options: dict[str, str]
    ) -> StructType:
        """Return the hard-coded Spark schema for the given table."""
        self._validate_table(table_name)
        return TABLE_SCHEMAS[table_name]

    def read_table_metadata(
        self, table_name: str, table_options: dict[str, str]
    ) -> dict:
        """Return metadata for the given table (all snapshot)."""
        self._validate_table(table_name)
        return dict(TABLE_METADATA[table_name])

    def read_table(
        self,
        table_name: str,
        start_offset: dict,
        table_options: dict[str, str],
    ) -> tuple[Iterator[dict], dict]:
        """Read all records for a snapshot table.

        Fetches report listings, identifies the latest reports for the
        requested type, downloads each Excel file, and yields rows as dicts.
        """
        self._validate_table(table_name)
        report_type = TABLE_TO_REPORT_TYPE[table_name]

        # Allow callers to specify time window via table_options
        created_at_from = (
            int(table_options["created_at_from"])
            if "created_at_from" in table_options
            else None
        )
        created_at_to = (
            int(table_options["created_at_to"])
            if "created_at_to" in table_options
            else None
        )
        all_reports = self._fetch_all_reports(created_at_from, created_at_to)
        if not all_reports:
            return iter([]), {}

        uuids = self._get_latest_report_uuids(all_reports, report_type)
        if not uuids:
            return iter([]), {}

        records: list[dict] = []
        for fsi_uuid in uuids:
            try:
                raw_df = self._download_report(fsi_uuid)
            except RuntimeError:
                continue

            if raw_df.empty:
                continue

            if table_name == "etmf_full_details":
                available_cols = [
                    c for c in FULL_DETAILS_COLUMN_MAP if c in raw_df.columns
                ]
                subset = raw_df[available_cols].rename(
                    columns=FULL_DETAILS_COLUMN_MAP
                )
                subset["fsi_uuid"] = fsi_uuid
                row_dicts = subset.where(subset.notna(), None).to_dict(
                    orient="records"
                )
            else:
                renamed = raw_df.rename(
                    columns=lambda x: x.lower().replace(" ", "_")
                )
                renamed["uuid"] = fsi_uuid
                row_dicts = renamed.where(renamed.notna(), None).to_dict(
                    orient="records"
                )

            records.extend(row_dicts)

        return iter(records), {}

    def _validate_table(self, table_name: str) -> None:
        """Raise ValueError if the table is not supported."""
        if table_name not in SUPPORTED_TABLES:
            raise ValueError(
                f"Table \'\'{table_name}\'\'  is not supported. "
                f"Supported tables: {SUPPORTED_TABLES}"
            )
