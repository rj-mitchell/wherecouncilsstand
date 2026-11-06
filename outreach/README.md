# Letters to councils

Requests for permission to read councils' meetings sites, where robots.txt forbids it or the site refuses the
crawler (docs/DECISIONS.md, 2: asked, not worked around). `scripts/outreach.py` writes them from the registry and the
addresses each council publishes; they are kept here as the record of who was asked, and when.

Each starts with its To: and Subject: lines, and is sent from the charity's Gmail account by Where MPs Stand's
`deploy/mail.sh` (its `docs/HOSTING.md`, "Email from the server"), so the links arrive as written:

    bash /opt/hansardgpt/deploy/mail.sh send /opt/wherecouncilsstand/outreach/2026-11/*.txt

A letter already sent is skipped, so the command is safe to repeat. Replies arrive in the account's inbox.

The server's address is never committed: the repository is public, and Cloudflare keeps the server's address
hidden. A letter to a council whose site refuses or doesn't answer the server says `[the server's IP address, as
given in the letter sent]` instead (the script writes it so, and `tests/test_outreach.py` fails if an address is
committed), and the address is filled in only when sending. Those letters are sent one at a time, not with the
command above: copy the letter outside the repository, keeping its file name (the record of letters already sent
goes by it), put the address in the copy, send the copy, and delete it. For example:

    cp /opt/wherecouncilsstand/outreach/2026-11/camden.txt /root/
    nano /root/camden.txt
    bash /opt/hansardgpt/deploy/mail.sh send /root/camden.txt && rm /root/camden.txt

Send them before running the command above, which would otherwise send them with the placeholder; once sent,
they are skipped. For the letter for post, put the address in before printing it.

A council that agrees by adding "User-agent: WhereCouncilsStand / Allow: /" to its robots.txt is read at the next
load (`sources/robots.py` checks rules under that name). One that agrees by email, leaving robots.txt as it is,
needs its permission recorded in the registry before it is read.

Councils that publish no email address get a letter for post instead, in the batch's `post/` folder (the send
command above doesn't take it). Print it, sign it and post it; it asks for a reply by email.
