from typing import List, Optional

from pydantic import BaseModel


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
    names: Optional[List[str]] = None


class StarterCatalogueAdoptResponse(BaseModel):
    created: int
    skipped: int
    created_items: List[str]
    skipped_items: List[str]
