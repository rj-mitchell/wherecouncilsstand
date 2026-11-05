# Letters to councils

Requests for permission to read councils' meetings sites, where robots.txt forbids it or the site refuses the
crawler (docs/DECISIONS.md, 2: asked, not worked around). `scripts/outreach.py` writes them from the registry and the
addresses each council publishes; they are kept here as the record of who was asked, and when.

Each starts with its To: and Subject: lines, and is sent from the charity's Gmail account by Where They Stand's
`deploy/mail.sh` (its `docs/HOSTING.md`, "Email from the server"), so the links arrive as written:

    bash /opt/hansardgpt/deploy/mail.sh send /opt/wherecouncilsstand/outreach/2026-11/*.txt

A letter already sent is skipped, so the command is safe to repeat. Replies arrive in the account's inbox.

A council that agrees by adding "User-agent: WhereCouncilsStand / Allow: /" to its robots.txt is read at the next
load (`sources/robots.py` checks rules under that name). One that agrees by email, leaving robots.txt as it is,
needs its permission recorded in the registry before it is read.

Councils that publish no email address get a letter for post instead, in the batch's `post/` folder (the send
command above doesn't take it). Print it, sign it and post it; it asks for a reply by email.
