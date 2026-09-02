# Make in-app notices authoritative and email optional

Every notification and receipt required by a production workflow will exist as a durable Authoritative Notice in PathLab and, where applicable, a downloadable signed artifact. Email is an optional Integration Gateway adapter enabled only for an Institution-supplied, qualified SMTP relay; an external Delivery Attempt and its failure are audited, but neither delivery success nor provider availability creates, confirms, deletes, or replaces the in-app record, and no hosted email or SMS service is mandatory.
