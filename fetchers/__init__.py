"""Fetcher package — one module per ATS type."""

from .fetch_greenhouse import fetch_greenhouse
from .fetch_lever import fetch_lever
from .fetch_workday import fetch_workday
from .fetch_ashby import fetch_ashby
from .fetch_amazon import fetch_amazon
from .fetch_sap import fetch_sap
from .fetch_servicenow import fetch_servicenow
from .fetch_eightfold import fetch_eightfold
from .fetch_phenom import fetch_phenom
from .fetch_turbohire import fetch_turbohire

__all__ = [
    "fetch_greenhouse",
    "fetch_lever",
    "fetch_workday",
    "fetch_ashby",
    "fetch_amazon",
    "fetch_sap",
    "fetch_servicenow",
    "fetch_eightfold",
    "fetch_phenom",
    "fetch_turbohire",
]
