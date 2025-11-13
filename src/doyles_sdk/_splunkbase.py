from typing import Any, Union

from doyles_sdk._classes import SplunkSession
from doyles_sdk._utilities import Doyles

SPLUNKBASE_URL = "https://splunkbase.splunk.com/api"
SPLUNKAPI_AUTH = "https://api.splunk.com/2.0/rest/login/splunk"
SPLUNKBASE_AUTH = SPLUNKBASE_URL + "/account:login"
SPLUNKBASE_SESSION_LIMIT = 10
SPLUNKBASE_RESULT_LIMIT = 100
INCLUDE_FIELDS = [
    "releases",
    "releases.splunk_compatibility",
    "releases.product_compatibility",
    "support",
]


class Splunkbase(SplunkSession):
    def __init__(self):
        super().__init__()
        self._cache = {}

    def _construct_url(self, appid) -> str:
        safe_appid = Doyles.url_quote(appid)
        include = ""
        if INCLUDE_FIELDS:
            include = f"&include={','.join(INCLUDE_FIELDS)}"

        return f"{SPLUNKBASE_URL}/v1/app/?appid={safe_appid}{include}"

    def search(self, appid: str) -> Union[dict[str, Any], None]:
        if appid in self._cache:
            return self._cache[appid]
        else:
            response = self.get(self._construct_url(appid))
            if response.status_code == 200:
                self._cache[appid] = response.json()["results"] or None
                return self._cache[appid]
