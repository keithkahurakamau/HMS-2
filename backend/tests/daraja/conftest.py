"""Register the models needed to configure SQLAlchemy mappers for this package.

tests/daraja has no app-level fixture that imports the full model graph the
way the live-server test suites do, so instantiating (or querying) any mapped
ORM model here is the first thing in the process to trigger SQLAlchemy's
configure_mappers(), which resolves every relationship() string reference
across the whole declarative registry, not just the class being touched.

MpesaTransaction.invoice is a string reference to Invoice, and Invoice in
turn references Patient by string, so both have to be imported somewhere
before any test in this package builds a real instance of a mapped model.
Tasks 1 to 3 avoided this by only making class-level assertions (inspecting
columns on the class, never instantiating a row); Task 4 needs real
MpesaConfig instances to exercise resolve_tenant_by_token, so the workaround
stops being enough and this import-only conftest is the fix.

No fixtures are defined here. Only the import side effect matters.
"""
from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction  # noqa: F401
from app.models.billing import Invoice  # noqa: F401
from app.models.patient import Patient  # noqa: F401
