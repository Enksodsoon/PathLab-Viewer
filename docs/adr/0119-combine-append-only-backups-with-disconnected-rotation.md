# Combine append-only backups with disconnected rotation

The always-online Backup Target will accept append-only production writes, while at least one verified encrypted recovery generation is rotated onto Institution-owned media that is physically disconnected whenever it is not being refreshed or tested. This base design qualifies production-host loss and a compromised production credential, not loss of an entire site or compromise of the backup administrator; a site-loss claim exists only when the disconnected copy is stored in a second Approved Data Location.
