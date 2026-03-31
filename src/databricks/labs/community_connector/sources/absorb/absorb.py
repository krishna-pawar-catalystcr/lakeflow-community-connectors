"""Absorb LMS connector for Lakeflow."""

import time
from datetime import datetime, timezone
from typing import Iterator

import requests
from pyspark.sql.types import StructType

from databricks.labs.community_connector.interface import LakeflowConnect
from databricks.labs.community_connector.sources.absorb.absorb_schemas import (
    SUPPORTED_TABLES,
    TABLE_METADATA,
    TABLE_SCHEMAS,
)

INITIAL_BACKOFF = 1
MAX_RETRIES = 3
RETRIABLE_STATUS_CODES = [429, 500, 503]

PORTAL_URL_MAP = {
    "US": "https://rest.myabsorb.com",
    "CA": "https://rest.myabsorb.ca",
    "EU": "https://rest.myabsorb.eu",
    "AU": "https://rest.myabsorb.com.au",
}


class AbsorbLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for Absorb LMS."""

    def __init__(self, options: dict[str, str]) -> None:
        """
        Initialize the Absorb connector with connection-level options.

        Expected options:
            - private_api_key: Private API key from Absorb portal settings.
            - username: Absorb account username.
            - password: Absorb account password.
            - portal_url: Portal region (US, CA, EU, AU). Defaults to US.
            - api_version: API version to use. Defaults to 2.
        """
        private_api_key = options.get("private_api_key")
        if not private_api_key:
            raise ValueError("Absorb connector requires 'private_api_key' in options")

        self._private_api_key = private_api_key
        self._username = options.get("username")
        self._password = options.get("password")
        self._api_version = options.get("api_version", "2")

        portal_url = options.get("portal_url", "US").upper()
        self._base_url = PORTAL_URL_MAP.get(portal_url, PORTAL_URL_MAP["US"])

        self._token: str | None = None

        self._init_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._verify_ssl = options.get("verify_ssl", "true").lower() != "false"

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _authenticate(self) -> str:
        """Authenticate using username/password and return the token."""
        if self._token:
            return self._token

        if not self._username or not self._password:
            raise ValueError(
                "Absorb connector requires 'username' and 'password' in options for authentication"
            )

        url = f"{self._base_url}/authenticate"
        payload = {
            "username": self._username,
            "password": self._password,
            "privateKey": self._private_api_key,
        }

        headers = {
            "x-api-key": self._private_api_key,
            "x-api-version": self._api_version,
        }

        response = self._session.post(url, json=payload, headers=headers, timeout=30, verify=self._verify_ssl)

        if response.status_code == 200:
            self._token = response.text.strip('"')
            return self._token

        if response.status_code == 400:
            raise ValueError(f"Authentication failed: missing required parameters - {response.text}")
        if response.status_code == 403:
            raise ValueError(f"Authentication failed: portal disabled - {response.text}")
        raise RuntimeError(f"Authentication failed: {response.status_code} {response.text}")

    def _get_auth_headers(self) -> dict:
        """Get headers with authentication."""
        token = self._authenticate()
        return {
            "x-api-key": self._private_api_key,
            "x-api-version": self._api_version,
            "Authorization": f"Bearer {token}",
        }

    def _request_with_retry(self, method: str, path: str, **kwargs) -> requests.Response:
        """Issue an API request, retrying on 429/500/503 with exponential backoff."""
        backoff = INITIAL_BACKOFF
        resp: requests.Response | None = None

        for attempt in range(MAX_RETRIES):
            headers = self._get_auth_headers()
            headers.update(kwargs.pop("headers", {}))

            url = f"{self._base_url}{path}"

            if method == "GET":
                resp = self._session.get(url, headers=headers, timeout=30, verify=self._verify_ssl, **kwargs)
            elif method == "POST":
                resp = self._session.post(url, headers=headers, timeout=30, verify=self._verify_ssl, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if resp.status_code not in RETRIABLE_STATUS_CODES:
                return resp

            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2

        return resp  # type: ignore[return-value]

    def list_tables(self) -> list[str]:
        """List all supported tables."""
        return SUPPORTED_TABLES.copy()

    def get_table_schema(self, table_name: str, table_options: dict[str, str]) -> StructType:
        """Fetch the schema of a table."""
        if table_name not in TABLE_SCHEMAS:
            raise ValueError(f"Unsupported table: {table_name!r}")
        return TABLE_SCHEMAS[table_name]

    def read_table_metadata(
        self, table_name: str, table_options: dict[str, str]
    ) -> dict:
        """Fetch metadata for the given table."""
        if table_name not in TABLE_METADATA:
            raise ValueError(f"Unsupported table: {table_name!r}")
        return TABLE_METADATA[table_name]

    def read_table(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        """Read records from a table and return raw JSON-like dictionaries."""
        if table_name not in TABLE_SCHEMAS:
            raise ValueError(f"Unsupported table: {table_name!r}")

        if table_name == "enrollments":
            return self._read_enrollments(table_name, start_offset, table_options)

        metadata = self.read_table_metadata(table_name, table_options)
        ingestion_type = metadata["ingestion_type"]

        if ingestion_type == "snapshot":
            return self._read_snapshot(table_name, table_options)

        cursor_field = metadata.get("cursor_field")
        if not cursor_field:
            raise ValueError(f"Table {table_name} has no cursor_field but uses incremental ingestion")
        return self._read_incremental(table_name, start_offset, table_options, cursor_field)

    def _read_enrollments(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        """Read enrollments using course-scoped endpoint /courses/{courseId}/enrollments."""
        max_records = int(table_options.get("max_records_per_batch", "200"))

        records = []
        course_page = 0
        course_limit = 1000
        last_course = None

        while len(records) < max_records:
            course_params = {"_offset": str(course_page), "_limit": str(course_limit)}
            resp = self._request_with_retry("GET", "/courses", params=course_params)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch courses for enrollments: {resp.status_code} {resp.text}")

            data = resp.json()
            courses = data.get("courses", [])
            returned_items = data.get("returnedItems", len(courses))

            if not courses:
                break

            for course in courses:
                course_id = course.get("id")
                if not course_id:
                    continue
                last_course = course

                enroll_page = 0
                enroll_limit = 1000
                while len(records) < max_records:
                    enroll_params = {"_offset": str(enroll_page), "_limit": str(enroll_limit)}
                    enroll_resp = self._request_with_retry(
                        "GET", f"/courses/{course_id}/enrollments", params=enroll_params
                    )
                    if enroll_resp.status_code != 200:
                        break

                    enroll_data = enroll_resp.json()
                    enrollments = enroll_data.get("enrollments", [])
                    enroll_returned = enroll_data.get("returnedItems", len(enrollments))

                    for enroll in enrollments:
                        enroll["courseId"] = course_id
                        enroll["courseName"] = course.get("name")
                        records.append(enroll)

                    if enroll_returned == 0 or len(enrollments) < enroll_limit:
                        break
                    enroll_page += 1

                if len(records) >= max_records:
                    break

            if returned_items == 0 or len(courses) < course_limit:
                break
            course_page += 1

        if not records:
            return iter([]), start_offset or {}

        end_offset = {"course_cursor": last_course.get("dateEdited")} if last_course else {}

        return iter(records), end_offset

    def _read_snapshot(
        self, table_name: str, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        """Full-refresh read with pagination."""
        country_id = table_options.get("country_id") if table_name == "provinces" else None
        if table_name == "provinces" and not country_id:
            return self._read_all_provinces()

        records = []
        page = 0
        limit = 1000

        while True:
            params: dict = {"_offset": str(page), "_limit": str(limit)}

            if table_name == "provinces" and country_id:
                params["countryId"] = country_id

            resp = self._request_with_retry("GET", f"/{table_name}", params=params)

            if resp.status_code != 200:
                raise RuntimeError(f"Failed to read {table_name}: {resp.status_code} {resp.text}")

            data = resp.json()
            returned_items = data.get("returnedItems", 0)

            if table_name == "provinces":
                items = data if isinstance(data, list) else []
            else:
                items_key = self._get_items_key(table_name)
                items = data.get(items_key, []) if isinstance(data, dict) else []

            records.extend(items)

            if returned_items == 0 or len(items) < limit:
                break

            page += 1

        return iter(records), {}

    def _read_all_provinces(self) -> tuple[Iterator[dict], dict]:
        """Read all provinces for all countries."""
        records = []
        country_page = 0
        country_limit = 1000

        while True:
            params = {"_offset": str(country_page), "_limit": str(country_limit)}
            resp = self._request_with_retry("GET", "/countries", params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch countries: {resp.status_code} {resp.text}")

            data = resp.json()
            returned_items = data.get("returnedItems", 0)
            if isinstance(data, dict):
                countries = data.get("countries", [])
            elif isinstance(data, list):
                countries = data
            else:
                countries = []

            if not countries:
                break

            for country in countries:
                country_id = country.get("id")
                country_code = country.get("countryCode")
                if not country_id:
                    continue

                prov_page = 0
                while True:
                    prov_params = {"_offset": str(prov_page), "_limit": "1000", "countryId": country_id}
                    prov_resp = self._request_with_retry("GET", "/provinces", params=prov_params)
                    if prov_resp.status_code != 200:
                        break

                    prov_data = prov_resp.json()
                    prov_returned = prov_data.get("returnedItems", 0) if isinstance(prov_data, dict) else 0
                    if isinstance(prov_data, list):
                        provinces = prov_data
                    elif isinstance(prov_data, dict):
                        provinces = prov_data.get("provinces", [])
                    else:
                        provinces = []

                    if not provinces:
                        break

                    for prov in provinces:
                        prov["countryId"] = country_id
                        prov["countryName"] = country.get("name")
                        prov["countryCode"] = country_code
                        records.append(prov)

                    if prov_returned == 0 or len(provinces) < 1000:
                        break
                    prov_page += 1

            if returned_items == 0 or len(countries) < country_limit:
                break
            country_page += 1

        return iter(records), {}

    def _read_incremental(
        self,
        table_name: str,
        start_offset: dict,
        table_options: dict[str, str],
        cursor_field: str,
    ) -> tuple[Iterator[dict], dict]:
        """Incremental read using page-based pagination."""
        cursor = start_offset.get("cursor") if start_offset else None

        if cursor and cursor >= self._init_ts:
            return iter([]), start_offset if start_offset else {}

        max_records = int(table_options.get("max_records_per_batch", "200"))
        limit = 1000

        records = []
        page = 0

        while len(records) < max_records:
            params: dict = {"_offset": str(page), "_limit": str(limit)}

            resp = self._request_with_retry("GET", f"/{table_name}", params=params)

            if resp.status_code != 200:
                raise RuntimeError(f"Failed to read {table_name}: {resp.status_code} {resp.text}")

            data = resp.json()
            returned_items = data.get("returnedItems", 0)
            items_key = self._get_items_key(table_name)
            items = data.get(items_key, []) if isinstance(data, dict) else []

            records.extend(items)

            if returned_items == 0 or len(items) < limit:
                break

            page += 1

        if not records:
            return iter([]), start_offset or {}

        last_cursor = records[-1].get(cursor_field)
        if not last_cursor:
            return iter([]), start_offset or {}

        end_offset = {"cursor": last_cursor}

        if start_offset and start_offset == end_offset:
            return iter([]), start_offset

        return iter(records), end_offset

    def _get_items_key(self, table_name: str) -> str | None:
        """Get the key name for the items array in the response."""
        mapping = {
            "users": "users",
            "departments": "departments",
            "courses": "courses",
            "enrollments": "enrollments",
            "groups": "groups",
            "roles": "roles",
            "countries": "countries",
            "provinces": None,
        }
        return mapping.get(table_name, table_name)
