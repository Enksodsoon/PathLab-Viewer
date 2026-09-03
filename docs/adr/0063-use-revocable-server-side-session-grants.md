# Use revocable server-side Session Grants

Browsers will receive only opaque Session Grants in Secure, HttpOnly, appropriately SameSite cookies; server state is revocable and rotates after authentication, privilege change, and recovery. Privileged sessions expire after 30 idle minutes or eight absolute hours, learner sessions after two idle hours or 12 absolute hours, and credential changes, grade publication, exports, and other classified sensitive actions require Step-Up Authentication. Bearer tokens in browser storage and non-expiring sessions are prohibited.
