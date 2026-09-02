# Create a dedicated Credential Ledger context

Credential Ledger becomes PathLab's fourteenth bounded context, co-deployed in `pathlab-control` but owning a separate database, roles, migrations, and outbox. Learning Catalog defines achievements and Assessment supplies approved outcomes, while Credential Ledger alone issues, supersedes, expires, and revokes Achievement Credentials so authentication secrets and educational credentials never share an owner or model.
