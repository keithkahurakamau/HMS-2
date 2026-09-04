from typing import List, Optional

from pydantic import BaseModel, Field

# Comfortably above any realistic catalogue size (the starter catalogue is a
# short, curated list) while still bounding a malformed or hostile payload
# from forcing an unbounded loop in adopt_into_inventory.
MAX_ADOPT_NAMES = 1000


class StarterCatalogueStatus(BaseModel):
    # Whether the operator has turned this feature on for the calling
    # hospital. False means the hospital shouldn't be shown the feature at
    # all, independent of whether the catalogue file itself has any rows.
    enabled: bool


class StarterCatalogueResponse(BaseModel):
    # Whether docs/seed/pharmacy-catalogue.csv currently has any usable
    # rows. False is a normal, expected state (operator hasn't loaded the
    # real list yet), not an error.
    available: bool
    products: List[str]


class StarterCatalogueAdoptRequest(BaseModel):
    # Product names to adopt, matched against the catalogue by normalised
    # name. Omit or send an empty list to adopt the entire catalogue.
    names: Optional[List[str]] = Field(
        default=None,
        max_length=MAX_ADOPT_NAMES,
        description=f"At most {MAX_ADOPT_NAMES} names per request.",
    )


class StarterCatalogueAdoptResponse(BaseModel):
    created: int
    skipped: int
    created_items: List[str]
    skipped_items: List[str]
