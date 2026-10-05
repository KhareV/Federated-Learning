"""NHM capstone product layer (CAPSTONE_PRODUCT_PROTOCOL_V1).

Additive orchestration layer ABOVE the frozen SOFTWARE_SYSTEM_V2 inference system. CAP-001
contains pure interface/contract code only: no simulator, no database, no server, no Clerk SDK.
The frozen inference contract (POST /v1/infer-window, API_SCHEMA_V1) is reused, never modified.
"""

PRODUCT_LINEAGE = "NHM_CAPSTONE_PRODUCT"
PROTOCOL_ID = "CAPSTONE_PRODUCT_PROTOCOL_V1"
