"""The state database, ``data/state.db``: the one thing that can't be rebuilt from councils' own sites, and what
its backups are called.

It is a small SQLite file opened through the Where They Stand sites' shared package (wts-core,
``wts_core.state``; its docs/adr/0005). The minutes themselves are in Parquet and the search index; nothing here is
needed to rebuild them.
"""

from __future__ import annotations

from wts_core.ops import AlertWording, BackupSpec

from councils.config import SITE

# What the site's backups are called and hold (`councils backup`, `restore`, `offsite`, `backup-check`; cli.py):
# councils-state-YYYY-MM-DD.sqlite.gz, the database gzipped, one a night. The nightly timer keeps 7 on the server
# (deploy/councils-backup.service); 60 are kept off site.
#
# A restore takes only a database with these two tables. They are the tables the site kept before the shared
# package, which every backup has, made before the move or after: on the day of the move the newest backup is one
# made before it, and it must still be possible to put it back. When the old tables are dropped (a later release),
# these names must change in the same release to tables of the package's (wts_spending, wts_briefings), or a
# restore would refuse every backup made after. The database is also marked as this site's when it is opened, and
# a backup marked as a sister site's is refused.
BACKUPS = BackupSpec(prefix="councils-state-", keep=14, keep_offsite=60, required_tables=("usage", "briefings"),
                     site=SITE.package)
# Nothing else that holds old rows (the copy of the database made before the one-off import, the weekly reports)
# is kept longer than the backups are: one a night, 60 kept off site, so about two months (the privacy page).
BACKUPS_KEPT_DAYS = BACKUPS.keep_offsite

# What `councils backup-check` says when backups or their off-site copies have stopped (each a sentence, as before)
BACKUP_ALERTS = AlertWording(
    no_backups="No backups have been made yet.",
    backup_stale="The last backup was made over two days ago ({name}).",
    server_only="Backups are kept on this server only: no off-site copy is set up.",
    no_offsite_yet="No off-site copy has been made yet; one is made with the next backup.",
    offsite_failed="The last off-site copy failed ({when}): {error}",
    offsite_stale="The last off-site copy was over two days ago ({day}).",
)
